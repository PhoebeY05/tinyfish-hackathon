# OpenAI + TinyFish Bird Classification Integration

## Overview

This implementation enables real-time bird classification using **OpenAI's Vision API** combined with **TinyFish** for evidence gathering from multiple ornithological sources.

## Architecture

```
User uploads ZIP with bird photos
    ↓
[API] POST /uploads (multipart file + geography)
    ↓
Background Job Processing
    ├─ Extract images from ZIP
    ├─ For each image:
    │   ├─ Classify with OpenAI Vision API
    │   │   └─ Returns: [species, confidence, scientific_name, alternates]
    │   │
    │   ├─ Gather evidence with TinyFish
    │   │   └─ Queries: eBird, BirdLife, Reddit, etc.
    │   │
    │   └─ Score dispute (confidence vs evidence agreement)
    │
    └─ Generate report:
        ├─ report.json (full structured data)
        ├─ citations.json (flattened sources)
        └─ index.html (rendered report)
    ↓
[API] GET /jobs/{id}/download → ZIP bundle
```

## Setup

### 1. Get OpenAI API Key

Visit <https://platform.openai.com/api-keys> and create a key.

### 2. Configure `.env`

```bash
# Enable OpenAI classification
ENABLE_OPENAI_CLASSIFICATION=true
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4-vision    # or gpt-4-turbo if it has vision

# Optional: Enable live TinyFish lookups
ENABLE_LIVE_LOOKUPS=true
TINYFISH_API_KEY=your-key-here
```

### 3. Install Dependencies

```bash
pip install openai
```

### 4. Restart Backend

```bash
python -m uvicorn backend.app:app --reload
```

## How Classification Works

### OpenAI Vision Prompt

The system sends each bird image to OpenAI with this prompt:

```
Analyze this bird image and identify the bird species.

Return JSON with:
- primary_species: Common name (e.g., "Red-tailed Hawk")
- scientific_name: Genus species (e.g., "Buteo jamaicensis")
- confidence: 0.0-1.0 confidence score
- alternate_1_species / alternate_1_confidence
- alternate_2_species / alternate_2_confidence
- reasoning: Why you think that
```

**Example Response:**

```json
{
  "primary_species": "Olive-backed Sunbird",
  "scientific_name": "Cinnyris jugularis",
  "confidence": 0.92,
  "alternate_1_species": "Brown-throated Sunbird",
  "alternate_1_confidence": 0.65,
  "alternate_2_species": "Yellow-vented Bulbul",
  "alternate_2_confidence": 0.38,
  "reasoning": "Identified by olive-green plumage on back, iridescent throat, and typical sunbird posture"
}
```

### TinyFish Evidence Gathering

For each classified species, TinyFish queries:

1. **eBird** - Recent sightings in the geography
2. **BirdLife International** - Species profile & habitat
3. **Field guides** - Similar species & distinguishing marks
4. **Reddit /r/whatsthisbird** - Community consensus (if confidence < 75%)

### Dispute Scoring

Compares OpenAI's confidence against evidence:

- **Major Dispute** - Confidence < 65% OR conflicting evidence ≥ supporting evidence
- **Minor Concern** - Confidence < 80% with some contradictions
- **No Dispute** - High confidence + supporting evidence agreement

## Programmatic Usage

### Use Case 1: Classify a Single Image

```python
from backend.config import load_settings
from backend.pipeline import classify_image_with_openai

settings = load_settings()
image_path = Path("bird.jpg")

result = classify_image_with_openai(image_path, settings)

print(f"Species: {result['primary']['common_name']}")
print(f"Confidence: {result['primary']['confidence']}")
print(f"Model: {result['model']}")
```

### Use Case 2: Classify + Get Evidence

```python
from backend.pipeline import (
    classify_image_with_openai,
    tinyfish_evidence_lookup
)

# 1. Classify
classification = classify_image_with_openai(Path("bird.jpg"), settings)
species = classification["primary"]["common_name"]

# 2. Get evidence
evidence = tinyfish_evidence_lookup(
    settings,
    species=species,
    geography="Singapore",
    include_community=True  # Query Reddit if needed
)

for source_data in evidence["evidence"]:
    print(f"{source_data['source']}: {source_data['extracted_claim']}")
```

### Use Case 3: Batch Classification

```bash
# See example_classify.py
python example_classify.py path/to/bird.jpg "Singapore"
```

## API Endpoints

**POST /uploads** - Start a classification job

```bash
curl -X POST http://localhost:8000/uploads \
  -F "photosZip=@birds.zip" \
  -F "geography=Singapore"

# Returns:
# {"jobId": "abc123", "status": "processing"}
```

**GET /jobs/{id}** - Check job status

```bash
curl http://localhost:8000/jobs/abc123

# Returns:
# {
#   "id": "abc123",
#   "status": "completed",
#   "progress": {
#     "current_step": "completed",
#     "total_images": 5,
#     "processed_images": 5
#   }
# }
```

**GET /jobs/{id}/results** - Get classification results

```bash
curl http://localhost:8000/jobs/abc123/results

# Returns full JSON with classifications, evidence, disputes, etc.
```

**GET /jobs/{id}/download** - Download report ZIP

```bash
curl http://localhost:8000/jobs/abc123/download > report.zip
```

## Fallback Behavior

If OpenAI API fails:

- System falls back to placeholder classifier (deterministic seed-based)
- Job completes with reduced confidence scores
- Pipeline continues normally (no hard failure)

## Costs & Optimization

| Operation | Cost | Notes |
|-----------|------|-------|
| OpenAI Vision (gpt-4-vision) | $0.01 per image | High quality, good for complex birds |
| OpenAI Vision (gpt-4-turbo) | $0.01 per image | Same quality, newer model |
| TinyFish (mock) | Free | No external API calls |
| TinyFish (live) | ~$0.001 per query | Based on sources queried |

**Optimization tips:**

- Use lower `temperature` (0.2) for consistent classifications
- Cache results by image hash if re-analyzing same photos
- Batch process images in off-peak hours
- Monitor token usage in OpenAI dashboard

## Example Output (report.json)

```json
{
  "job_id": "abc123",
  "created_at": "2026-03-28T12:34:56Z",
  "images": [
    {
      "image_id": "bird1.jpg",
      "primary_prediction": {
        "common_name": "Olive-backed Sunbird",
        "scientific_name": "Cinnyris jugularis",
        "confidence": 0.92,
        "model": "gpt-4-vision"
      },
      "alternate_candidates": [
        {"common_name": "Brown-throated Sunbird", "confidence": 0.65}
      ],
      "location_context": {
        "geography": "Singapore",
        "last_spotted_text": "Last reported in Singapore 3 days ago",
        "source": "eBird"
      },
      "evidence": [
        {
          "source": "TinyFish/eBird",
          "type": "live_sighting",
          "extracted_claim": "Last reported in Singapore 3 days ago",
          "supports": "Olive-backed Sunbird",
          "contradicts": null,
          "citation_url": "https://ebird.org/..."
        }
      ],
      "confidence_dispute": {
        "status": "no_dispute",
        "reason": ""
      },
      "review_status": "review_ready"
    }
  ]
}
```

## Troubleshooting

**Error: ENABLE_OPENAI_CLASSIFICATION=true requires OPENAI_API_KEY**

```bash
# Fix: Add OPENAI_API_KEY to .env and restart
export OPENAI_API_KEY=sk-your-key
```

**Error: Rate limit exceeded**

```bash
# Wait a few seconds or use gpt-4-turbo instead of gpt-4-vision
# Monitor usage: https://platform.openai.com/account/rate-limits
```

**Images not being classified correctly**

```bash
# Test with a clear, well-lit image
# Check OpenAI response in logs for reasoning
# Adjust prompt in classify_image_with_openai() if needed
```

**TinyFish evidence not appearing**

```bash
# Set ENABLE_LIVE_LOOKUPS=false (default) to use mock data
# Or provide valid TINYFISH_API_KEY for real lookups
```

## Next Steps

1. ✅ Integration complete - upload ZIP to `/uploads`
2. 📊 Monitor classification accuracy - check logs
3. 🔧 Tune OpenAI prompt for your bird species list
4. 🌍 Expand geography regions (currently "Singapore")
5. 🔌 Connect live TinyFish API when ready
