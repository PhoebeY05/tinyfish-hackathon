# TinyFish Bird Report MVP Base

This repository now includes a Python backend base for a bird-photo upload and report workflow that matches your requested architecture:

- Upload a `.zip` of bird photos
- Create a background batch job
- Produce per-image species predictions (top 3 candidates)
- Run TinyFish-based web evidence gathering stubs (including eBird recency line shape)
- Compute dispute status and review recommendations
- Return JSON results and downloadable report bundle

## What This MVP Base Includes

- React + Tailwind responsive frontend in `frontend/`
- FastAPI backend with TinyFish orchestration in `backend/`
- Background job pipeline for evidence collection in `backend/pipeline.py`
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

### Backend & Frontend (Production Build)

1. Install Python dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

1. Install and build React frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

1. Configure environment

```bash
cp .env.example .env
```

1. Start server

```bash
uvicorn backend.app:app --host 0.0.0.0 --port 3000
```

1. Open app

`http://localhost:3000`

### Frontend Development (with Hot Reload)

In a separate terminal, run the Vite dev server while backend runs on port 3000:

```bash
cd frontend
npm run dev
```

This proxies API requests to the backend and enables React hot module reloading.

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
frontend/
  src/
    components/
      DisputeBadge.jsx
      EvidencePanel.jsx
      Hero.jsx
      ImageCard.jsx
      ProgressBar.jsx
      ResultsSection.jsx
      UploadSection.jsx
    App.jsx
    index.css
    main.jsx
  index.html
  package.json
  tailwind.config.js
  vite.config.js
data/
  uploads/
  reports/
requirements.txt
```

## Frontend Features

- **Responsive Design**: Mobile-first with Tailwind CSS breakpoints (sm, md, lg)
- **Real-time Progress**: Polls backend job status and displays live progress bar
- **Evidence Panel**: Expandable accordion showing all sources and citations
- **Dispute Visualization**: Color-coded badges for no_dispute, minor_disagreement, major_disagreement
- **Download Integration**: Direct download link for report ZIP bundle per job
