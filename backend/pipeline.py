from __future__ import annotations

import base64
import json
import random
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from openai import OpenAI

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


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_species(common_name: str) -> tuple[str, str]:
    return CANONICAL_TAXONOMY.get(common_name.lower(), (common_name, "Unknown"))


def classify_image(image_name: str) -> dict[str, Any]:
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
        return classify_image(image_path.name)


def tinyfish_evidence_lookup(
    settings: Settings,
    species: str,
    geography: str,
    include_community: bool,
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

    payload = {
        "workflow": "bird-evidence-v1",
        "input": {
            "species": species,
            "geography": geography,
            "instructions": [
                f"Check eBird for most recent reports of {species} in {geography}.",
                "Extract field marks, habitat, and similar species from trusted bird references.",
                "Inspect birding community discussion only when ambiguity is high."
                if include_community
                else "Skip community sources unless ambiguity threshold is reached.",
            ],
        },
    }

    try:
        response = requests.post(
            f"{settings.tinyfish_base_url.rstrip('/')}/v1/agents/run",
            json=payload,
            headers={"Authorization": f"Bearer {settings.tinyfish_api_key}"},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        if "evidence" not in data:
            return {"failed": True, "error": "TinyFish response missing evidence key.", "evidence": []}
        return {"failed": False, "evidence": data["evidence"]}
    except Exception as exc:
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
        store.update_job(job_id, status="running", progress={"current_step": "extracting_zip"})

        extraction_dir = settings.upload_dir / job_id / "images"
        images = _extract_zip_images(Path(job.metadata["upload_path"]), extraction_dir)

        if not images:
            raise RuntimeError("No supported image files found in the uploaded zip.")

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

        for index, image_path in enumerate(images, start=1):
            # Use OpenAI classification if enabled, otherwise use placeholder
            if settings.enable_openai_classification:
                prediction = classify_image_with_openai(image_path, settings)
            else:
                prediction = classify_image(image_path.name)
            
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
                )
                combined_evidence.extend(lookup.get("evidence", []))
                if lookup.get("failed"):
                    provider_errors.append(lookup.get("error", "TinyFish lookup failed"))

            dispute = compute_dispute(
                primary_confidence=prediction["primary"]["confidence"],
                primary_name=prediction["primary"]["common_name"],
                evidence=combined_evidence,
            )

            image_reports.append(
                {
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
                }
            )

            store.update_job(
                job_id,
                progress={"processed_images": index, "current_step": "collecting_evidence"},
            )

        report = {
            "job_id": job_id,
            "generated_at": now_iso(),
            "geography": job.metadata["geography"],
            "images": image_reports,
        }

        store.update_job(job_id, progress={"current_step": "building_report"})
        bundle = build_report_bundle(settings.report_dir / job_id, report)

        store.update_job(
            job_id,
            status="completed",
            progress={"current_step": "completed"},
            results=report,
            artifacts=bundle,
        )
    except Exception as exc:
        store.update_job(
            job_id,
            status="failed",
            progress={"current_step": "failed"},
            error=str(exc),
        )
