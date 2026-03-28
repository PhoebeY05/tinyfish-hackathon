# TinyFish Bird Report MVP Base

This repository now includes a Python backend base for a bird-photo upload and report workflow that matches your requested architecture:

- Upload a `.zip` of bird photos
- Create a background batch job
- Produce per-image species predictions (top 3 candidates)
- Run TinyFish-based web evidence gathering stubs (including eBird recency line shape)
- Compute dispute status and review recommendations
- Return JSON results and downloadable report bundle

## What This MVP Base Includes

- Frontend upload/results app in `public/`
- Backend API in `backend/app.py`
- Background job pipeline in `backend/pipeline.py`
- Report artifact generation in `data/reports/`

## API Endpoints

- `POST /uploads`
  - Form field: `photosZip` (required)
  - Optional field: `geography` (defaults to `Singapore`)
  - Returns: `{ jobId, status }`

- `GET /jobs/{id}`
  - Returns job status and progress counters

- `GET /jobs/{id}/results`
  - Returns full JSON report payload when complete

- `GET /jobs/{id}/download`
  - Downloads `bird-report.zip` with:
    - `report.json`
    - `citations.json`
    - `index.html`
    - image previews

## Run Locally

1. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Configure environment

```bash
cp .env.example .env
```

1. Start server

```bash
uvicorn backend.app:app --reload --host 0.0.0.0 --port 3000
```

1. Open app

`http://localhost:3000`

## Environment

- `PORT` (default: `3000`)
- `UPLOAD_DIR` (default: `data/uploads`)
- `REPORT_DIR` (default: `data/reports`)
- `ENABLE_LIVE_LOOKUPS` (`false` by default)
- `TINYFISH_API_KEY` (required when `ENABLE_LIVE_LOOKUPS=true`)
- `TINYFISH_BASE_URL` (optional, defaults to `https://api.tinyfish.ai`)

The app follows fail-fast startup for critical config: if live lookups are enabled and TinyFish credentials are missing, startup fails immediately.

TinyFish orchestration is implemented in the Python backend pipeline (`backend/pipeline.py`) rather than frontend or JS service modules.

## Notes About Scope

This base intentionally keeps V1 realistic:

- Uses a TinyFish adapter layer that is easy to expand
- Does not hard-code a promise of scraping 17 websites in MVP
- Uses tiered source strategy and only calls community sources for low-confidence ambiguity

## Test Plan Checklist (Manual)

- Upload valid zip and receive per-image reports
- Verify eBird-style recency line is present in location context
- Verify ambiguous species can trigger dispute status
- Verify source failure path still returns results with labeled evidence
- Verify factual claims have citation URLs or are marked as model inference
- Verify downloadable zip contains report and artifact files

## Project Layout

```text
backend/
  app.py
  config.py
  job_store.py
  pipeline.py
public/
  index.html
  app.js
data/
  uploads/
  reports/
```
