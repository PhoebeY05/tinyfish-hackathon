from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import (BackgroundTasks, FastAPI, File, Form, HTTPException,
                     Query, UploadFile)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import load_settings
from .job_store import JobStore
from .pipeline import QUIZ_FALLBACK_SPECIES, process_job
from .quiz_store import QuizStore
from .rarity_leaderboard import RarityLeaderboardStore

# Ensure backend picks up .env values when started via uvicorn.
load_dotenv()

settings = load_settings()
store = JobStore()
quiz_store = QuizStore(settings.quiz_db_path)
rarity_store = RarityLeaderboardStore(settings.rarity_leaderboard_db_path)

settings.upload_dir.mkdir(parents=True, exist_ok=True)
settings.report_dir.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="TinyFish Bird Report MVP")
app.mount("/uploads", StaticFiles(directory=str(settings.upload_dir)), name="uploads")


class QuizSubmissionCreate(BaseModel):
    userId: str = Field(min_length=1, max_length=128)
    quizId: str = Field(min_length=1, max_length=128)
    score: float
    totalQuestions: int = Field(ge=0)
    answers: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RarityLeaderboardSubmit(BaseModel):
    jobId: str = Field(min_length=1, max_length=128)
    participantId: str = Field(min_length=1, max_length=128)
    displayName: str = Field(min_length=1, max_length=128)


@app.get("/api/quiz/species")
def quiz_species(
    geography: str = Query("Global"),
    limit: int = Query(250, ge=20, le=500),
) -> dict[str, object]:
    species = [
        {"commonName": name, "aliases": [name, name.replace("-", " ")]}
        for name in QUIZ_FALLBACK_SPECIES[:limit]
    ]
    return {
        "species": species,
        "source": "all-birds-list",
        "live": False,
        "count": len(species),
        "geography": geography,
    }


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

    return FileResponse(path=zip_path, filename="report.zip", media_type="application/zip")


@app.post("/quiz/submissions", status_code=201)
def create_quiz_submission(payload: QuizSubmissionCreate) -> dict[str, Any]:
    submission = quiz_store.create_submission(
        user_id=payload.userId,
        quiz_id=payload.quizId,
        score=payload.score,
        total_questions=payload.totalQuestions,
        answers=payload.answers,
        metadata=payload.metadata,
    )
    return {"submission": submission}


@app.get("/quiz/submissions")
def list_quiz_submissions(
    userId: str | None = None,
    quizId: str | None = None,
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")

    submissions = quiz_store.list_submissions(
        user_id=userId,
        quiz_id=quizId,
        limit=limit,
    )
    return {"submissions": submissions}


@app.get("/quiz/submissions/{submission_id}")
def get_quiz_submission(submission_id: str) -> dict[str, Any]:
    submission = quiz_store.get_submission(submission_id)
    if not submission:
        raise HTTPException(status_code=404, detail="Quiz submission not found")
    return {"submission": submission}


@app.post("/leaderboard/rarity/submit", status_code=201)
def submit_rarity_score(payload: RarityLeaderboardSubmit) -> dict[str, Any]:
    job = store.get_job(payload.jobId)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Job is not completed yet")
    if not job.results:
        raise HTTPException(status_code=409, detail="Completed job has no report results")

    ranking = rarity_store.submit_job_score(
        participant_id=payload.participantId,
        display_name=payload.displayName,
        job_id=payload.jobId,
        report=job.results,
    )
    return ranking


@app.get("/leaderboard/rarity")
def get_rarity_leaderboard(
    limit: int = 50,
    geography: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    entries = rarity_store.get_leaderboard(limit=limit, geography=geography)
    return {"entries": entries}


@app.get("/leaderboard/rarity/participants/{participant_id}")
def get_participant_history(participant_id: str, limit: int = 20) -> dict[str, list[dict[str, Any]]]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    entries = rarity_store.get_participant_history(participant_id=participant_id, limit=limit)
    return {"entries": entries}


# Serve React build output from frontend/dist after all API routes
# This allows API routes to take precedence and SPA fallback for unmatched routes
build_dir = Path("frontend/dist").resolve()
if build_dir.exists():
    app.mount("/", StaticFiles(directory=str(build_dir), html=True), name="frontend")
