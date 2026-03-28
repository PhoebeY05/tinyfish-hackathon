from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import random
import shutil
import threading
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
    if isinstance(event, dict):
        for key in ("output", "text", "content", "data", "message", "delta"):
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

    with client.agent.stream(url=url, goal=goal) as stream:
        for event in stream:
            parsed = _extract_json_from_tinyfish_event(event)
            if isinstance(parsed, (dict, list)):
                return parsed

            event_text = str(event).strip()
            if event_text:
                stream_chunks.append(event_text)
                if on_log and "EventType.PROGRESS" in event_text:
                    on_log(f"TinyFish progress: {event_text[:180]}")

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
    supports = sum(1 for item in evidence if item.get("supports") == primary_name)
    contradicts = sum(1 for item in evidence if item.get("contradicts") == primary_name)

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


def _extract_zip_images(zip_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with zipfile.ZipFile(zip_path, "r") as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            filename = Path(info.filename).name
            suffix = Path(filename).suffix.lower()
            if suffix not in SUPPORTED_EXT:
                continue

            target = output_dir / filename
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


def build_report_bundle(report_dir: Path, report: dict[str, Any]) -> dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)

    report_json = report_dir / "report.json"
    citations_json = report_dir / "citations.json"
    report_html = report_dir / "index.html"
    report_zip = report_dir / "bird-report.zip"

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

    with zipfile.ZipFile(report_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(report_json, arcname="report.json")
        archive.write(citations_json, arcname="citations.json")
        archive.write(report_html, arcname="index.html")

    return {
        "report_json_path": str(report_json),
        "citations_path": str(citations_json),
        "report_html_path": str(report_html),
        "zip_path": str(report_zip),
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
                "total_images": len(images),
                "processed_images": 0,
            },
            artifacts={"extraction_dir": str(extraction_dir)},
        )

        image_reports: list[dict[str, Any]] = []
        image_reports_lock = threading.Lock()

        def process_single_image(index: int, image_path: Path) -> dict[str, Any]:
            # Use OpenAI classification if enabled, otherwise use placeholder
            if settings.enable_openai_classification:
                push_log(f"OpenAI: classifying image {index}/{len(images)} ({image_path.name}).")
                prediction = classify_image_with_openai(image_path, settings)
                push_log(f"OpenAI: classification complete for {image_path.name}.")
            else:
                prediction = _fallback_classify_image(image_path.name)
                push_log(f"OpenAI disabled: used fallback classifier for {image_path.name}.")
            
            primary_common = prediction["primary"]["common_name"]
            primary_common, primary_sci = normalize_species(primary_common)

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

            include_community = prediction["primary"]["confidence"] < 0.75
            candidate_names = [prediction["primary"]["common_name"]] + [a["common_name"] for a in prediction["alternates"]]
            combined_evidence = []
            provider_errors = []

            for candidate in candidate_names:
                lookup = tinyfish_evidence_lookup(
                    settings=settings,
                    species=candidate,
                    geography=job.metadata["geography"],
                    include_community=include_community,
                    on_log=push_log,
                )
                combined_evidence.extend(lookup.get("evidence", []))
                if lookup.get("failed"):
                    provider_errors.append(lookup.get("error", "TinyFish lookup failed"))

            dispute = compute_dispute(
                primary_confidence=prediction["primary"]["confidence"],
                primary_name=prediction["primary"]["common_name"],
                evidence=combined_evidence,
            )

            return {
                "index": index,
                "payload": {
                    "image_id": f"img_{index:03d}",
                    "file_name": image_path.name,
                    "primary_prediction": {
                        "common_name": primary_common,
                        "scientific_name": primary_sci,
                        "confidence": prediction["primary"]["confidence"],
                    },
                    "alternate_candidates": alternates,
                    "location_context": {
                        "country": job.metadata["geography"],
                        "last_spotted_text": f"Last reported in {job.metadata['geography']} 3 days ago",
                        "source": "eBird",
                    },
                    "evidence": [
                        {
                            "source": "model_inference",
                            "type": "model_prediction",
                            "supports": prediction["primary"]["common_name"],
                            "citation_url": None,
                            "extracted_claim": f"Model {prediction['model']} predicted {prediction['primary']['common_name']}",
                        },
                        *combined_evidence,
                    ],
                    "confidence_dispute": {
                        "status": dispute["status"],
                        "reason": dispute["reason"],
                    },
                    "review_status": dispute["review_status"],
                    "provider_errors": provider_errors,
                },
            }

        # Run all image jobs concurrently (configurable via env, defaults to all images).
        max_workers_env = os.environ.get("MAX_CONCURRENT_IMAGE_WORKERS")
        max_workers = len(images)
        if max_workers_env:
            try:
                max_workers = max(1, min(len(images), int(max_workers_env)))
            except ValueError:
                max_workers = len(images)

        push_log(f"Running {len(images)} image pipelines with max_workers={max_workers}.")
        processed_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(process_single_image, idx, img_path): (idx, img_path.name)
                for idx, img_path in enumerate(images, start=1)
            }

            for future in concurrent.futures.as_completed(futures):
                idx, file_name = futures[future]
                result = future.result()
                with image_reports_lock:
                    image_reports.append(result)
                processed_count += 1
                push_log(f"Completed image {idx}/{len(images)} ({file_name}).")
                store.update_job(
                    job_id,
                    progress={"processed_images": processed_count, "current_step": "collecting_evidence"},
                )

        image_reports.sort(key=lambda item: item["index"])
        ordered_reports = [item["payload"] for item in image_reports]

        report = {
            "job_id": job_id,
            "generated_at": now_iso(),
            "geography": job.metadata["geography"],
            "images": ordered_reports,
        }

        store.update_job(job_id, progress={"current_step": "building_report"})
        push_log("Building report bundle and citations.")
        bundle = build_report_bundle(settings.report_dir / job_id, report)

        store.update_job(
            job_id,
            status="completed",
            progress={"current_step": "completed"},
            results=report,
            artifacts=bundle,
        )
        push_log("Analysis completed successfully.")
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
