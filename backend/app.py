from __future__ import annotations

import os
import shutil
from pathlib import Path
from uuid import uuid4

import psycopg2
from dotenv import load_dotenv
from fastapi import (BackgroundTasks, FastAPI, File, Form, HTTPException,
                     Query, UploadFile)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import load_settings
from .job_store import JobStore
from .pipeline import get_quiz_species_catalog, process_job

# Ensure backend picks up .env values when started via uvicorn.
load_dotenv()

settings = load_settings()
store = JobStore()
DATABASE_URL = os.environ.get("DATABASE_URL")

settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.report_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="TinyFish Bird Report MVP")


@app.on_event("startup")
def startup_database_connection() -> None:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is required for PostgreSQL connection.")

    app.state.db_conn = psycopg2.connect(DATABASE_URL, sslmode="require")


@app.on_event("shutdown")
def shutdown_database_connection() -> None:
    db_conn = getattr(app.state, "db_conn", None)
    if db_conn:
        db_conn.close()


@app.get("/api/quiz/species")
def quiz_species(
    geography: str = Query("Global"),
    limit: int = Query(250, ge=20, le=500),
) -> dict[str, object]:
    return get_quiz_species_catalog(settings=settings, geography=geography, limit=limit)


@app.post("/uploads")
async def upload_zip(
    background_tasks: BackgroundTasks,
    photosZip: UploadFile = File(...),
    geography: str = Form("Singapore"),
) -> dict[str, str]:
    if not photosZip.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Only .zip uploads are supported.")

    target_dir = settings.upload_dir / "incoming"
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid4()}-{photosZip.filename}"

    with target_path.open("wb") as out:
        shutil.copyfileobj(photosZip.file, out)

    job = store.create_job(
        {
            "geography": geography or "Singapore",
            "upload_path": str(target_path),
            "upload_original_name": photosZip.filename,
        }
    )

    background_tasks.add_task(process_job, job.id, store, settings)
    return {"jobId": job.id, "status": job.status}


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "id": job.id,
        "status": job.status,
        "progress": job.progress,
        "error": job.error,
    }


@app.get("/jobs/{job_id}/results")
def job_results(job_id: str) -> dict:
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail={"status": job.status, "progress": job.progress})

    return job.results or {}


@app.get("/jobs/{job_id}/download")
def job_download(job_id: str):
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Report bundle not ready")

    zip_path = job.artifacts.get("zip_path")
    if not zip_path or not Path(zip_path).exists():
        raise HTTPException(status_code=404, detail="Report zip not found")

    return FileResponse(path=zip_path, filename=f"{job_id}-bird-report.zip", media_type="application/zip")


# Serve React build output from frontend/dist after all API routes
# This allows API routes to take precedence and SPA fallback for unmatched routes
build_dir = Path("frontend/dist").resolve()
if build_dir.exists():
    app.mount("/", StaticFiles(directory=str(build_dir), html=True), name="frontend")
