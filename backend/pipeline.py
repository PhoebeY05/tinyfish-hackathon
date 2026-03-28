from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import random
import re
import shutil
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from tinyfish import TinyFish

from .config import Settings
from .job_store import JobStore

SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".webp"}

CANONICAL_TAXONOMY = {
    "olive-backed sunbird": ("Olive-backed Sunbird", "Cinnyris jugularis"),
    "brown-throated sunbird": ("Brown-throated Sunbird", "Anthreptes malacensis"),
    "yellow-vented bulbul": ("Yellow-vented Bulbul", "Pycnonotus goiavier"),
    "asian koel": ("Asian Koel", "Eudynamys scolopaceus"),
    "collared kingfisher": ("Collared Kingfisher", "Todiramphus chloris"),
}

CANDIDATES = [
    ("Olive-backed Sunbird", 0.84),
    ("Brown-throated Sunbird", 0.61),
    ("Yellow-vented Bulbul", 0.49),
    ("Asian Koel", 0.44),
    ("Collared Kingfisher", 0.41),
]

QUIZ_FALLBACK_SPECIES = [
    "Asian Koel",
    "Collared Kingfisher",
    "Olive-backed Sunbird",
    "Yellow-vented Bulbul",
    "Brahminy Kite",
    "Black-naped Oriole",
    "Javan Myna",
    "White-throated Kingfisher",
    "Scarlet-backed Flowerpecker",
    "Eurasian Tree Sparrow",
    "Blue-tailed Bee-eater",
    "House Crow",
    "Pink-necked Green Pigeon",
    "Crimson Sunbird",
    "Common Tailorbird",
    "Pacific Swallow",
    "Little Egret",
    "Cattle Egret",
    "Black-crowned Night Heron",
    "White-breasted Waterhen",
    "Common Myna",
    "Barn Swallow",
    "Oriental Magpie-Robin",
    "Zebra Dove",
    "Spotted Dove",
    "Red Junglefowl",
    "Long-tailed Shrike",
    "Ashy Tailorbird",
    "Grey Heron",
    "Purple Heron",
    "Striated Heron",
    "Pied Fantail",
    "Dollarbird",
    "Rufous Woodpecker",
    "Lineated Barbet",
    "Coppersmith Barbet",
    "Greater Coucal",
    "Lesser Coucal",
    "Black Baza",
    "Changeable Hawk-Eagle",
    "Crested Goshawk",
    "Shikra",
    "White-bellied Sea Eagle",
    "Grey-headed Fish Eagle",
    "Peregrine Falcon",
    "Black-winged Kite",
    "Eurasian Kestrel",
    "Rose-ringed Parakeet",
    "Blue-crowned Hanging Parrot",
    "Red-breasted Parakeet",
    "Chestnut Munia",
    "Scaly-breasted Munia",
    "White-rumped Munia",
    "Baya Weaver",
    "Common Iora",
    "Yellow-browed Warbler",
    "Arctic Warbler",
    "Pallas's Grasshopper Warbler",
    "Oriental Reed Warbler",
    "Mugimaki Flycatcher",
    "Asian Brown Flycatcher",
    "Brown Shrike",
    "Tiger Shrike",
    "Black Drongo",
    "Ashy Drongo",
    "Greater Racket-tailed Drongo",
    "Common Kingfisher",
    "Stork-billed Kingfisher",
    "Oriental Pied Hornbill",
    "Black Hornbill",
    "Crested Serpent Eagle",
    "Indian Cuckoo",
    "Plaintive Cuckoo",
    "Savanna Nightjar",
    "Large-tailed Nightjar",
    "Little Tern",
    "Whiskered Tern",
    "Common Sandpiper",
    "Wood Sandpiper",
    "Pied Imperial Pigeon",
    "Green Imperial Pigeon",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_species(common_name: str) -> tuple[str, str]:
    return CANONICAL_TAXONOMY.get(common_name.lower(), (common_name, "Unknown"))


def _fallback_classify_image(image_name: str) -> dict[str, Any]:
    seed = sum(ord(ch) for ch in image_name.lower())
    random.seed(seed)
    start = random.randint(0, len(CANDIDATES) - 1)
    picks = [CANDIDATES[(start + i) % len(CANDIDATES)] for i in range(3)]
    return {
        "primary": {"common_name": picks[0][0], "confidence": round(picks[0][1], 2)},
        "alternates": [
            {"common_name": picks[1][0], "confidence": round(max(0.0, picks[1][1] - 0.05), 2)},
            {"common_name": picks[2][0], "confidence": round(max(0.0, picks[2][1] - 0.1), 2)},
        ],
        "model": "baseline-placeholder-v1",
    }


def _normalize_quiz_species_item(item: Any) -> dict[str, Any] | None:
    if isinstance(item, str):
        common_name = item.strip()
        if not common_name:
            return None
        return {
            "commonName": common_name,
            "aliases": [common_name, common_name.replace("-", " ")],
        }

    if isinstance(item, dict):
        common_name = (
            item.get("commonName")
            or item.get("common_name")
            or item.get("species")
            or item.get("name")
            or ""
        ).strip()
        if not common_name:
            return None

        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        aliases = [str(alias).strip() for alias in aliases if str(alias).strip()]
        aliases.extend([common_name, common_name.replace("-", " ")])

        result = {
            "commonName": common_name,
            "aliases": sorted(set(aliases), key=lambda name: name.lower()),
        }

        if item.get("wikipediaTitle"):
            result["wikipediaTitle"] = item["wikipediaTitle"]

        return result

    return None


def _extract_json_from_text(text: str) -> dict[str, Any] | list[Any] | None:
    raw = text.strip()
    if not raw:
        return None

    candidates = [raw]
    if "```json" in raw:
        candidates.append(raw.split("```json", 1)[1].split("```", 1)[0].strip())
    if "```" in raw:
        candidates.append(raw.split("```", 1)[1].split("```", 1)[0].strip())

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return None


def _extract_json_from_tinyfish_event(event: Any) -> dict[str, Any] | list[Any] | None:
    # Check for result_json attribute (completion events may have this)
    if hasattr(event, "result_json") and event.result_json:
        if isinstance(event.result_json, str):
            parsed = _extract_json_from_text(event.result_json)
        else:
            parsed = event.result_json
        if isinstance(parsed, (dict, list)):
            return parsed
    
    if isinstance(event, dict):
        # Include result_json in the keys to check
        for key in ("output", "text", "content", "data", "message", "delta", "result_json"):
            value = event.get(key)
            if isinstance(value, (dict, list)):
                return value
            if isinstance(value, str):
                parsed = _extract_json_from_text(value)
                if parsed is not None:
                    return parsed

    if isinstance(event, str):
        return _extract_json_from_text(event)

    parsed = _extract_json_from_text(str(event))
    return parsed


def _build_tinyfish_client(settings: Settings) -> TinyFish:
    if settings.tinyfish_api_key:
        os.environ.setdefault("TINYFISH_API_KEY", settings.tinyfish_api_key)

    try:
        return TinyFish(api_key=settings.tinyfish_api_key)
    except TypeError:
        return TinyFish()


def _run_tinyfish_agent(settings: Settings, url: str, goal: str) -> dict[str, Any] | list[Any]:
    return _run_tinyfish_agent_with_logs(settings=settings, url=url, goal=goal, on_log=None)


def _run_tinyfish_agent_with_logs(
    settings: Settings,
    url: str,
    goal: str,
    on_log: Callable[[str], None] | None,
) -> dict[str, Any] | list[Any]:
    client = _build_tinyfish_client(settings)
    stream_chunks: list[str] = []
    event_count = 0

    with client.agent.stream(url=url, goal=goal) as stream:
        for event in stream:
            event_count += 1
            
            # Log event metadata for debugging
            event_meta = ""
            if hasattr(event, "type"):
                event_meta += f" type={event.type}"
            if hasattr(event, "status"):
                event_meta += f" status={event.status}"
            if hasattr(event, "result_json"):
                event_meta += " [HAS_result_json]"
            
            if on_log:
                on_log(f"Event {event_count}:{event_meta} | {str(event)[:120]}")
            
            # Try to extract JSON from this event
            parsed = _extract_json_from_tinyfish_event(event)
            if isinstance(parsed, (dict, list)):
                if on_log:
                    on_log(f"✓ Extracted JSON from event {event_count}")
                return parsed

            # Collect full stream text for fallback parsing
            event_text = str(event).strip()
            if event_text:
                stream_chunks.append(event_text)
                if on_log and "EventType.PROGRESS" in event_text:
                    on_log(f"TinyFish progress: {event_text[:180]}")

    if on_log:
        on_log(f"Stream completed. Total events: {event_count}. Attempting full stream parsing...")
    
    parsed = _extract_json_from_text("\n".join(stream_chunks))
    if isinstance(parsed, (dict, list)):
        return parsed

    raise RuntimeError("TinyFish stream completed without valid JSON output.")


def get_quiz_species_catalog(settings: Settings, geography: str, limit: int = 250) -> dict[str, Any]:
    fallback_species = [
        {"commonName": name, "aliases": [name, name.replace("-", " ")]} for name in QUIZ_FALLBACK_SPECIES[:limit]
    ]

    if not settings.enable_live_lookups:
        return {
            "species": fallback_species,
            "source": "fallback",
            "live": False,
            "count": len(fallback_species),
        }

    try:
        tinyfish_result = _run_tinyfish_agent(
            settings=settings,
            url="https://en.wikipedia.org/wiki/List_of_birds_by_common_name",
            goal=(
                f"Create a quiz species pool for {geography}. "
                f"Return JSON only with key 'species' as an array up to {limit} items. "
                "Each item must be an object with commonName and optional aliases array."
            ),
        )
        data = tinyfish_result if isinstance(tinyfish_result, dict) else {"species": tinyfish_result}

        raw_species = data.get("species") or data.get("birds") or data.get("items") or []
        normalized: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in raw_species:
            parsed = _normalize_quiz_species_item(item)
            if not parsed:
                continue
            key = parsed["commonName"].lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(parsed)
            if len(normalized) >= limit:
                break

        if len(normalized) < 20:
            return {
                "species": fallback_species,
                "source": "fallback",
                "live": False,
                "count": len(fallback_species),
                "error": "TinyFish returned too few species for quiz pool.",
            }

        return {
            "species": normalized,
            "source": "tinyfish",
            "live": True,
            "count": len(normalized),
        }
    except Exception as exc:
        return {
            "species": fallback_species,
            "source": "fallback",
            "live": False,
            "count": len(fallback_species),
            "error": str(exc),
        }


def classify_image_with_openai(image_path: Path, settings: Settings) -> dict[str, Any]:
    """
    Classify a bird image using OpenAI's Vision API.
    
    Returns a dict with the same structure as classify_image():
    {
        "primary": {"common_name": str, "confidence": float},
        "alternates": [{"common_name": str, "confidence": float}, ...],
        "model": "gpt-4-vision" or similar
    }
    """
    client = OpenAI(api_key=settings.openai_api_key)
    
    # Read and encode image as base64
    with open(image_path, "rb") as img_file:
        image_data = base64.standard_b64encode(img_file.read()).decode("utf-8")
    
    # Determine image media type
    ext = image_path.suffix.lower()
    media_type_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    media_type = media_type_map.get(ext, "image/jpeg")
    
    # Call OpenAI Vision API
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{image_data}",
                        },
                    },
                    {
                        "type": "text",
                        "text": """Analyze this bird image and identify the bird species.
                        
Return a JSON response with this exact structure:
{
  "primary_species": "Common Name (e.g., Red-tailed Hawk)",
  "scientific_name": "Genus species (e.g., Buteo jamaicensis)",
  "confidence": 0.85,
  "alternate_1_species": "Common Name",
  "alternate_1_scientific_name": "Genus species",
  "alternate_1_confidence": 0.65,
  "alternate_2_species": "Common Name",
  "alternate_2_scientific_name": "Genus species",
  "alternate_2_confidence": 0.45,
  "reasoning": "Brief reason for identification"
}

If the image does not contain a bird, set confidence to 0 and explain in reasoning.
Only return valid JSON, no other text.""",
                    },
                ],
            }
        ],
        temperature=0.2,  # Lower temp for more consistent classifications
    )
    
    # Parse OpenAI response
    try:
        content = response.choices[0].message.content
        # Extract JSON from the response (in case there's extra text)
        import json as json_module

        # Try to find JSON in the response
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]
        else:
            json_str = content
        
        data = json_module.loads(json_str)
        
        return {
            "primary": {
                "common_name": data.get("primary_species", "Unknown"),
                "confidence": float(data.get("confidence", 0.5)),
            },
            "alternates": [
                {
                    "common_name": data.get("alternate_1_species", "Unknown"),
                    "confidence": float(data.get("alternate_1_confidence", 0.3)),
                },
                {
                    "common_name": data.get("alternate_2_species", "Unknown"),
                    "confidence": float(data.get("alternate_2_confidence", 0.2)),
                },
            ],
            "model": settings.openai_model,
            "reasoning": data.get("reasoning", ""),
        }
    except Exception as e:
        print(f"Error parsing OpenAI response: {e}")
        # Fallback to placeholder if parsing fails
        return _fallback_classify_image(image_path.name)


def tinyfish_evidence_lookup(
    settings: Settings,
    species: str,
    geography: str,
    include_community: bool,
    on_log: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    retrieval_time = now_iso()

    if not settings.enable_live_lookups:
        evidence = [
            {
                "source": "TinyFish/eBird",
                "type": "live_sighting",
                "extracted_claim": f"Last reported in {geography}: 3 days ago",
                "supports": species,
                "contradicts": None,
                "citation_url": "https://ebird.org/",
                "retrieval_timestamp": retrieval_time,
            },
            {
                "source": "TinyFish/BirdLife",
                "type": "species_profile",
                "extracted_claim": "Observed in gardens and urban edges in Southeast Asia.",
                "supports": species,
                "contradicts": None,
                "citation_url": "https://www.birdlife.org/",
                "retrieval_timestamp": retrieval_time,
            },
        ]
        if include_community:
            evidence.append(
                {
                    "source": "TinyFish/Reddit-birding",
                    "type": "community_debate",
                    "extracted_claim": "Community notes confusion with similar sunbird species.",
                    "supports": None,
                    "contradicts": species,
                    "citation_url": "https://www.reddit.com/r/whatsthisbird/",
                    "retrieval_timestamp": retrieval_time,
                }
            )
        return {"failed": False, "evidence": evidence}

    try:
        tinyfish_result = _run_tinyfish_agent_with_logs(
            settings=settings,
            url="https://ebird.org/",
            goal=(
                f"Gather evidence for bird species '{species}' in {geography}. "
                "Return JSON only with key 'evidence'. "
                "Each evidence item should include source, type, extracted_claim, supports, contradicts, citation_url, retrieval_timestamp. "
                + (
                    "Include community/reddit signals only when ambiguity is high."
                    if include_community
                    else "Do not include community/reddit sources unless necessary."
                )
            ),
            on_log=on_log,
        )
        data = tinyfish_result if isinstance(tinyfish_result, dict) else {"evidence": tinyfish_result}
        if "evidence" not in data:
            return {"failed": True, "error": "TinyFish response missing evidence key.", "evidence": []}
        return {"failed": False, "evidence": data["evidence"]}
    except Exception as exc:
        if on_log:
            on_log(f"TinyFish error for '{species}': {exc}")
        return {"failed": True, "error": str(exc), "evidence": []}


def compute_dispute(primary_confidence: float, primary_name: str, evidence: list[dict[str, Any]]) -> dict[str, str]:
    primary_key = _normalize_species_key(primary_name)
    supports = 0
    contradicts = 0
    for item in evidence:
        if _evidence_item_weight(item) <= 0:
            continue
        if _normalize_species_key(item.get("supports")) == primary_key:
            supports += 1
        if _normalize_species_key(item.get("contradicts")) == primary_key:
            contradicts += 1

    if primary_confidence < 0.65 or (contradicts > 0 and contradicts >= supports):
        return {
            "status": "major_disagreement",
            "reason": "Conflicting evidence or low model confidence.",
            "review_status": "review_recommended",
        }
    if primary_confidence < 0.8:
        return {
            "status": "minor_disagreement",
            "reason": "Top candidates remain visually confusable.",
            "review_status": "review_ready",
        }
    return {
        "status": "no_dispute",
        "reason": "Model and source evidence aligned.",
        "review_status": "review_ready",
    }


def _normalize_species_key(name: str | None) -> str:
    return (name or "").strip().lower()


def _evidence_item_weight(item: dict[str, Any]) -> float:
    evidence_type = str(item.get("type") or "").strip().lower()
    source = str(item.get("source") or "").strip().lower()

    # Base model confidence already captures model inference.
    if evidence_type == "model_prediction" or source == "model_inference":
        return 0.0
    if evidence_type == "live_sighting":
        return 1.0
    if evidence_type == "species_profile":
        return 0.8
    if evidence_type == "community_debate":
        return 0.45
    return 0.6


def compute_aggregated_confidence(
    model_confidence: float,
    primary_name: str,
    evidence: list[dict[str, Any]],
) -> float:
    base = max(0.0, min(1.0, float(model_confidence)))
    primary_key = _normalize_species_key(primary_name)
    if not primary_key:
        return base

    support_weight = 0.0
    contradict_weight = 0.0
    for item in evidence:
        weight = _evidence_item_weight(item)
        if weight <= 0:
            continue

        supports_key = _normalize_species_key(item.get("supports"))
        contradicts_key = _normalize_species_key(item.get("contradicts"))
        if supports_key == primary_key:
            support_weight += weight
        if contradicts_key == primary_key:
            contradict_weight += weight

    total_weight = support_weight + contradict_weight
    if total_weight <= 0:
        return base

    net_support = (support_weight - contradict_weight) / total_weight  # -1 to +1
    evidence_strength = min(1.0, total_weight / 4.0)
    max_shift = 0.28
    adjusted = base + (net_support * evidence_strength * max_shift)
    return round(max(0.0, min(1.0, adjusted)), 2)


def _loading_location_context(geography: str) -> dict[str, str]:
    return {
        "country": geography,
        "last_spotted_text": "Loading recent sightings from TinyFish...",
        "source": "TinyFish",
    }


def _location_context_from_evidence(geography: str, evidence: list[dict[str, Any]]) -> dict[str, str]:
    for item in evidence:
        extracted_claim = item.get("extracted_claim")
        if item.get("type") == "live_sighting" and isinstance(extracted_claim, str) and extracted_claim.strip():
            return {
                "country": geography,
                "last_spotted_text": extracted_claim.strip(),
                "source": item.get("source") or "TinyFish",
            }

    return {
        "country": geography,
        "last_spotted_text": "No recent sightings found from TinyFish yet.",
        "source": "TinyFish",
    }


def _extract_zip_images(zip_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []
    used_names: set[str] = set()

    def _is_ignored_zip_entry(entry_name: str) -> bool:
        path = Path(entry_name)
        parts = path.parts
        base = path.name
        if not base:
            return True
        # Ignore hidden/system metadata entries commonly produced by macOS ZIP tools.
        if any(part == "__MACOSX" for part in parts):
            return True
        if base.startswith("._") or base.startswith("."):
            return True
        return False

    def _dedupe_name(original_name: str) -> str:
        if original_name not in used_names:
            used_names.add(original_name)
            return original_name

        stem = Path(original_name).stem
        suffix = Path(original_name).suffix
        counter = 2
        while True:
            candidate = f"{stem}_{counter}{suffix}"
            if candidate not in used_names:
                used_names.add(candidate)
                return candidate
            counter += 1

    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            if _is_ignored_zip_entry(info.filename):
                continue
            filename = Path(info.filename).name
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_EXT:
                continue

            target = output_dir / _dedupe_name(filename)
            with archive.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)

    return extracted


def _render_html_report(report: dict[str, Any]) -> str:
    cards = []
    for item in report["images"]:
        alt = ", ".join(
            f"{candidate['common_name']} ({candidate['confidence']})"
            for candidate in item["alternate_candidates"]
        )
        cards.append(
            """
<section style='border:1px solid #ddd;padding:12px;margin-bottom:12px;border-radius:8px;'>
  <h3>{primary}</h3>
  <p><strong>Scientific name:</strong> {sci}</p>
  <p><strong>Confidence:</strong> {conf}</p>
  <p><strong>Alternates:</strong> {alt}</p>
  <p><strong>Location context:</strong> {loc}</p>
  <p><strong>Dispute:</strong> {dispute}</p>
  <p><strong>Review:</strong> {review}</p>
</section>
""".format(
                primary=item["primary_prediction"]["common_name"],
                sci=item["primary_prediction"]["scientific_name"],
                conf=item["primary_prediction"]["confidence"],
                alt=alt,
                loc=item["location_context"]["last_spotted_text"],
                dispute=item["confidence_dispute"]["status"],
                review=item["review_status"],
            )
        )

    return """
<!doctype html>
<html>
  <head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>Bird Report</title></head>
  <body style='font-family: Georgia, serif; max-width: 980px; margin: 24px auto;'>
    <h1>Bird Report</h1>
    <p>Generated at: {generated_at}</p>
    {cards}
  </body>
</html>
""".format(generated_at=report["generated_at"], cards="\n".join(cards))


def _safe_species_folder_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9 _-]+", "", (name or "Unknown Species").strip())
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "Unknown Species"


def build_report_bundle(report_dir: Path, report: dict[str, Any], extraction_dir: Path | None = None) -> dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)

    report_json = report_dir / "report.json"
    citations_json = report_dir / "citations.json"
    report_html = report_dir / "index.html"
    report_zip = report_dir / "bird-report.zip"
    species_groups_dir = report_dir / "species_groups"
    species_groups_zip = report_dir / "species-groups.zip"

    citations = []
    for image in report["images"]:
        for evidence in image["evidence"]:
            if evidence.get("citation_url"):
                citations.append(
                    {
                        "image_id": image["image_id"],
                        "source": evidence.get("source"),
                        "citation_url": evidence.get("citation_url"),
                    }
                )

    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    citations_json.write_text(json.dumps(citations, indent=2), encoding="utf-8")
    report_html.write_text(_render_html_report(report), encoding="utf-8")

    if species_groups_dir.exists():
        shutil.rmtree(species_groups_dir)
    species_groups_dir.mkdir(parents=True, exist_ok=True)

    if extraction_dir and extraction_dir.exists():
        per_species_counts: dict[str, int] = {}
        for image in report.get("images", []):
            file_name = image.get("file_name")
            if not file_name:
                continue

            source_path = extraction_dir / file_name
            if not source_path.exists():
                continue

            species_name = image.get("primary_prediction", {}).get("common_name", "Unknown Species")
            folder_name = _safe_species_folder_name(species_name)
            target_folder = species_groups_dir / folder_name
            target_folder.mkdir(parents=True, exist_ok=True)

            stem = source_path.stem
            suffix = source_path.suffix
            per_species_counts.setdefault(folder_name, 0)
            per_species_counts[folder_name] += 1
            ordinal = per_species_counts[folder_name]
            target_name = f"{ordinal:03d}_{stem}{suffix}"

            shutil.copy2(source_path, target_folder / target_name)

    with zipfile.ZipFile(species_groups_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for file_path in species_groups_dir.rglob("*"):
            if file_path.is_file():
                archive.write(file_path, arcname=str(file_path.relative_to(species_groups_dir)))

    with zipfile.ZipFile(report_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(report_json, arcname="report.json")
        archive.write(citations_json, arcname="citations.json")
        archive.write(report_html, arcname="index.html")
        archive.write(species_groups_zip, arcname="species-groups.zip")

    return {
        "report_json_path": str(report_json),
        "citations_path": str(citations_json),
        "report_html_path": str(report_html),
        "zip_path": str(report_zip),
        "species_groups_dir": str(species_groups_dir),
        "species_groups_zip_path": str(species_groups_zip),
    }


def process_job(job_id: str, store: JobStore, settings: Settings) -> None:
    job = store.get_job(job_id)
    if not job:
        return

    try:
        progress_logs: list[str] = []
        logs_lock = threading.Lock()

        def push_log(message: str) -> None:
            entry = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {message}"
            with logs_lock:
                progress_logs.append(entry)
                logs_snapshot = progress_logs[-120:]
            store.update_job(
                job_id,
                progress={
                    "logs": logs_snapshot,
                    "latest_log": entry,
                },
            )

        push_log("Analysis started.")
        store.update_job(job_id, status="running", progress={"current_step": "extracting_zip"})
        push_log("Extracting images from uploaded zip.")

        extraction_dir = settings.upload_dir / job_id / "images"
        images = _extract_zip_images(Path(job.metadata["upload_path"]), extraction_dir)

        if not images:
            raise RuntimeError("No supported image files found in the uploaded zip.")

        push_log(f"Found {len(images)} supported images.")

        store.update_job(
            job_id,
            progress={
                "current_step": "classifying_images",
                "phase": "classification",
                "total_images": len(images),
                "processed_images": 0,
                "classification_completed": False,
                "evidence_completed": False,
            },
            artifacts={"extraction_dir": str(extraction_dir)},
        )

        classified_results: list[dict[str, Any]] = []

        def process_single_image(index: int, image_path: Path) -> dict[str, Any]:
            # Phase 1: classify only (no evidence lookups in this stage).
            if settings.enable_openai_classification:
                push_log(f"OpenAI: classifying image {index}/{len(images)} ({image_path.name}).")
                prediction = classify_image_with_openai(image_path, settings)
                push_log(f"OpenAI: classification complete for {image_path.name}.")
            else:
                prediction = _fallback_classify_image(image_path.name)
                push_log(f"OpenAI disabled: used fallback classifier for {image_path.name}.")

            primary_common, primary_sci = normalize_species(prediction["primary"]["common_name"])

            alternates = []
            for alt in prediction["alternates"]:
                alt_common, alt_sci = normalize_species(alt["common_name"])
                alternates.append(
                    {
                        "common_name": alt_common,
                        "scientific_name": alt_sci,
                        "confidence": alt["confidence"],
                    }
                )

            return {
                "index": index,
                "file_name": image_path.name,
                "prediction": prediction,
                "primary_common": primary_common,
                "primary_sci": primary_sci,
                "alternates": alternates,
                "include_community": prediction["primary"]["confidence"] < 0.75,
            }

        # Run all image jobs concurrently (configurable via env, defaults to all images).
        max_workers_env = os.environ.get("MAX_CONCURRENT_IMAGE_WORKERS")
        max_workers = len(images)
        if max_workers_env:
            try:
                max_workers = max(1, min(len(images), int(max_workers_env)))
            except ValueError:
                max_workers = len(images)

        push_log(f"Running classification for {len(images)} images with max_workers={max_workers}.")
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_single_image, idx, img_path): (idx, img_path.name)
                for idx, img_path in enumerate(images, start=1)
            }

            for future in concurrent.futures.as_completed(futures):
                idx, file_name = futures[future]
                result = future.result()
                classified_results.append(result)
                processed_count += 1
                push_log(f"Classification completed for image {idx}/{len(images)} ({file_name}).")
                store.update_job(
                    job_id,
                    progress={
                        "processed_images": processed_count,
                        "current_step": "classifying_images",
                        "phase": "classification",
                    },
                )

        classified_results.sort(key=lambda item: item["index"])
        push_log("Classification phase completed. Grouping images by predicted species.")

        species_groups: dict[str, dict[str, Any]] = {}
        for item in classified_results:
            key = (item["primary_common"] or "Unknown Species").strip().lower()
            if not key:
                key = "unknown species"

            group = species_groups.setdefault(
                key,
                {
                    "species_common": item["primary_common"],
                    "species_scientific": item["primary_sci"],
                    "include_community": False,
                    "image_indices": [],
                },
            )
            group["include_community"] = group["include_community"] or item["include_community"]
            group["image_indices"].append(item["index"])

        ordered_reports: list[dict[str, Any]] = []
        for item in classified_results:
            prediction = item["prediction"]
            all_evidence = [
                {
                    "source": "model_inference",
                    "type": "model_prediction",
                    "supports": prediction["primary"]["common_name"],
                    "citation_url": None,
                    "extracted_claim": f"Model {prediction['model']} predicted {prediction['primary']['common_name']}",
                }
            ]

            dispute = compute_dispute(
                primary_confidence=compute_aggregated_confidence(
                    model_confidence=prediction["primary"]["confidence"],
                    primary_name=prediction["primary"]["common_name"],
                    evidence=all_evidence,
                ),
                primary_name=prediction["primary"]["common_name"],
                evidence=all_evidence,
            )

            ordered_reports.append(
                {
                    "image_id": f"img_{item['index']:03d}",
                    "file_name": item["file_name"],
                    "primary_prediction": {
                        "common_name": item["primary_common"],
                        "scientific_name": item["primary_sci"],
                        "confidence": compute_aggregated_confidence(
                            model_confidence=prediction["primary"]["confidence"],
                            primary_name=prediction["primary"]["common_name"],
                            evidence=all_evidence,
                        ),
                    },
                    "alternate_candidates": item["alternates"],
                    "location_context": _loading_location_context(job.metadata["geography"]),
                    "evidence": all_evidence,
                    "confidence_dispute": {
                        "status": dispute["status"],
                        "reason": dispute["reason"],
                    },
                    "review_status": dispute["review_status"],
                    "provider_errors": [],
                }
            )

        report = {
            "job_id": job_id,
            "generated_at": now_iso(),
            "geography": job.metadata["geography"],
            "images": ordered_reports,
        }

        store.update_job(job_id, progress={"current_step": "building_report", "phase": "classification"})
        push_log("Building report bundle and citations from classification output.")
        bundle = build_report_bundle(settings.report_dir / job_id, report, extraction_dir=extraction_dir)

        store.update_job(
            job_id,
            status="completed",
            progress={
                "current_step": "completed",
                "phase": "classification",
                "classification_completed": True,
                "evidence_completed": False,
                "evidence_background_running": True,
                "notification": "Classification report ready. TinyFish evidence is continuing in background.",
            },
            results=report,
            artifacts=bundle,
        )
        push_log("Classification output is ready. Download is available now.")

        total_species_groups = len(species_groups)
        evidence_workers_env = os.environ.get("MAX_CONCURRENT_EVIDENCE_WORKERS")
        evidence_workers = min(4, max(1, total_species_groups)) if total_species_groups else 1
        if evidence_workers_env:
            try:
                evidence_workers = max(1, min(total_species_groups or 1, int(evidence_workers_env)))
            except ValueError:
                evidence_workers = min(4, max(1, total_species_groups)) if total_species_groups else 1

        def enrich_evidence_in_background() -> None:
            try:
                classified_by_index = {item["index"]: item for item in classified_results}

                store.update_job(
                    job_id,
                    progress={
                        "current_step": "collecting_evidence",
                        "phase": "evidence",
                        "evidence_background_running": True,
                        "evidence_completed": False,
                        "total_species_groups": total_species_groups,
                        "processed_species_groups": 0,
                        "notification": "TinyFish evidence search running in background.",
                    },
                )
                push_log(
                    f"Starting background evidence search for {total_species_groups} species groups with max_workers={evidence_workers}."
                )

                evidence_by_image_index: dict[int, list[dict[str, Any]]] = {}
                provider_errors_by_image_index: dict[int, list[str]] = {}

                group_items = list(species_groups.values())

                def fetch_group_evidence(group: dict[str, Any], group_ordinal: int) -> dict[str, Any]:
                    species_name = group["species_common"]
                    group_indexes: list[int] = group["image_indices"]
                    push_log(
                        f"TinyFish[{species_name}]: collecting evidence for species group {group_ordinal}/{total_species_groups} "
                        f"({len(group_indexes)} images)."
                    )

                    def species_log(message: str) -> None:
                        push_log(f"TinyFish[{species_name}]: {message}")

                    lookup = tinyfish_evidence_lookup(
                        settings=settings,
                        species=species_name,
                        geography=job.metadata["geography"],
                        include_community=bool(group["include_community"]),
                        on_log=species_log,
                    )
                    group_errors: list[str] = []
                    if lookup.get("failed"):
                        group_errors.append(lookup.get("error", "TinyFish lookup failed"))

                    return {
                        "species_name": species_name,
                        "group_indexes": group_indexes,
                        "group_evidence": lookup.get("evidence", []),
                        "group_errors": group_errors,
                    }

                processed_groups = 0
                with concurrent.futures.ThreadPoolExecutor(max_workers=evidence_workers) as executor:
                    futures = {
                        executor.submit(fetch_group_evidence, group, idx): (idx, group["species_common"])
                        for idx, group in enumerate(group_items, start=1)
                    }

                    for future in concurrent.futures.as_completed(futures):
                        _, species_name = futures[future]
                        result = future.result()
                        group_indexes = result["group_indexes"]
                        group_evidence = result["group_evidence"]
                        group_errors = result["group_errors"]

                        for image_index in group_indexes:
                            evidence_by_image_index.setdefault(image_index, []).extend(group_evidence)
                            if group_errors:
                                provider_errors_by_image_index.setdefault(image_index, []).extend(group_errors)

                        processed_groups += 1
                        push_log(
                            f"TinyFish[{species_name}]: evidence completed ({processed_groups}/{total_species_groups} groups done)."
                        )

                        latest_job = store.get_job(job_id)
                        current_report = latest_job.results if latest_job and latest_job.results else None
                        if current_report and isinstance(current_report.get("images"), list):
                            updated_images: list[dict[str, Any]] = []
                            for image in current_report["images"]:
                                image_copy = dict(image)
                                image_id = str(image_copy.get("image_id", ""))
                                try:
                                    image_index = int(image_id.split("_")[-1])
                                except Exception:
                                    updated_images.append(image_copy)
                                    continue

                                if image_index in group_indexes:
                                    existing_evidence = image_copy.get("evidence", [])
                                    image_copy["evidence"] = [*existing_evidence, *group_evidence]

                                    existing_errors = image_copy.get("provider_errors", [])
                                    image_copy["provider_errors"] = [*existing_errors, *group_errors]
                                    image_copy["location_context"] = _location_context_from_evidence(
                                        job.metadata["geography"],
                                        image_copy["evidence"],
                                    )

                                    classified_item = classified_by_index.get(image_index)
                                    if classified_item:
                                        prediction = classified_item["prediction"]
                                        aggregated_confidence = compute_aggregated_confidence(
                                            model_confidence=prediction["primary"]["confidence"],
                                            primary_name=prediction["primary"]["common_name"],
                                            evidence=image_copy["evidence"],
                                        )
                                        existing_primary = image_copy.get("primary_prediction", {})
                                        image_copy["primary_prediction"] = {
                                            **existing_primary,
                                            "confidence": aggregated_confidence,
                                        }
                                        dispute = compute_dispute(
                                            primary_confidence=aggregated_confidence,
                                            primary_name=prediction["primary"]["common_name"],
                                            evidence=image_copy["evidence"],
                                        )
                                        image_copy["confidence_dispute"] = {
                                            "status": dispute["status"],
                                            "reason": dispute["reason"],
                                        }
                                        image_copy["review_status"] = dispute["review_status"]

                                updated_images.append(image_copy)

                            incremental_report = {
                                "job_id": current_report.get("job_id", job_id),
                                "generated_at": now_iso(),
                                "geography": current_report.get("geography", job.metadata["geography"]),
                                "images": updated_images,
                            }
                            store.update_job(job_id, results=incremental_report)

                        store.update_job(
                            job_id,
                            progress={
                                "current_step": "collecting_evidence",
                                "phase": "evidence",
                                "processed_species_groups": processed_groups,
                                "total_species_groups": total_species_groups,
                            },
                        )

                enriched_images: list[dict[str, Any]] = []
                for item in classified_results:
                    prediction = item["prediction"]
                    image_evidence = evidence_by_image_index.get(item["index"], [])
                    provider_errors = provider_errors_by_image_index.get(item["index"], [])

                    all_evidence = [
                        {
                            "source": "model_inference",
                            "type": "model_prediction",
                            "supports": prediction["primary"]["common_name"],
                            "citation_url": None,
                            "extracted_claim": f"Model {prediction['model']} predicted {prediction['primary']['common_name']}",
                        },
                        *image_evidence,
                    ]

                    dispute = compute_dispute(
                        primary_confidence=compute_aggregated_confidence(
                            model_confidence=prediction["primary"]["confidence"],
                            primary_name=prediction["primary"]["common_name"],
                            evidence=all_evidence,
                        ),
                        primary_name=prediction["primary"]["common_name"],
                        evidence=all_evidence,
                    )

                    enriched_images.append(
                        {
                            "image_id": f"img_{item['index']:03d}",
                            "file_name": item["file_name"],
                            "primary_prediction": {
                                "common_name": item["primary_common"],
                                "scientific_name": item["primary_sci"],
                                "confidence": compute_aggregated_confidence(
                                    model_confidence=prediction["primary"]["confidence"],
                                    primary_name=prediction["primary"]["common_name"],
                                    evidence=all_evidence,
                                ),
                            },
                            "alternate_candidates": item["alternates"],
                            "location_context": _location_context_from_evidence(
                                job.metadata["geography"],
                                all_evidence,
                            ),
                            "evidence": all_evidence,
                            "confidence_dispute": {
                                "status": dispute["status"],
                                "reason": dispute["reason"],
                            },
                            "review_status": dispute["review_status"],
                            "provider_errors": provider_errors,
                        }
                    )

                enriched_report = {
                    "job_id": job_id,
                    "generated_at": now_iso(),
                    "geography": job.metadata["geography"],
                    "images": enriched_images,
                }

                push_log("Rebuilding report bundle with TinyFish evidence.")
                enriched_bundle = build_report_bundle(settings.report_dir / job_id, enriched_report, extraction_dir=extraction_dir)

                store.update_job(
                    job_id,
                    status="completed",
                    progress={
                        "current_step": "evidence_completed",
                        "phase": "evidence",
                        "evidence_background_running": False,
                        "evidence_completed": True,
                        "classification_completed": True,
                        "processed_species_groups": total_species_groups,
                        "total_species_groups": total_species_groups,
                        "notification": "Evidence search completed.",
                    },
                    results=enriched_report,
                    artifacts=enriched_bundle,
                )
                push_log("Evidence search completed and report updated.")
            except Exception as exc:
                push_log(f"Evidence background process failed: {exc}")
                store.update_job(
                    job_id,
                    progress={
                        "current_step": "evidence_failed",
                        "phase": "evidence",
                        "evidence_background_running": False,
                        "evidence_completed": False,
                        "notification": "Evidence search failed. Classification report is still available.",
                    },
                )

        threading.Thread(target=enrich_evidence_in_background, daemon=True).start()
    except Exception as exc:
        prior_logs = job.progress.get("logs", []) if isinstance(job.progress.get("logs"), list) else []
        store.update_job(
            job_id,
            progress={
                "logs": [*prior_logs, f"[error] {exc}"][-120:],
                "latest_log": f"[error] {exc}",
            },
        )
        store.update_job(
            job_id,
            status="failed",
            progress={"current_step": "failed"},
            error=str(exc),
        )
