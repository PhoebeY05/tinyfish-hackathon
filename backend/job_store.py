from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Job:
    id: str
    status: str
    created_at: str
    updated_at: str
    progress: dict[str, Any]
    metadata: dict[str, Any]
    artifacts: dict[str, Any] = field(default_factory=dict)
    results: dict[str, Any] | None = None
    error: str | None = None


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()

    def create_job(self, metadata: dict[str, Any]) -> Job:
        with self._lock:
            job_id = str(uuid4())
            now = _now_iso()
            job = Job(
                id=job_id,
                status="queued",
                created_at=now,
                updated_at=now,
                progress={"total_images": 0, "processed_images": 0, "current_step": "queued"},
                metadata=metadata,
            )
            self._jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update_job(self, job_id: str, **updates: Any) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None

            for key, value in updates.items():
                if key == "progress" and isinstance(value, dict):
                    job.progress = {**job.progress, **value}
                elif key == "artifacts" and isinstance(value, dict):
                    job.artifacts = {**job.artifacts, **value}
                else:
                    setattr(job, key, value)

            job.updated_at = _now_iso()
            return job
