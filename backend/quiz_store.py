from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QuizStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_store()

    def _initialize_store(self) -> None:
        if not self.db_path.exists():
            self._write_db({"submissions": []})
            return

        try:
            payload = json.loads(self.db_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("submissions", []), list):
                self._write_db({"submissions": []})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._write_db({"submissions": []})

    def _read_db(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {"submissions": []}
        try:
            return json.loads(self.db_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"submissions": []}

    def _write_db(self, payload: dict[str, Any]) -> None:
        self.db_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def create_submission(
        self,
        *,
        user_id: str,
        quiz_id: str,
        score: float,
        total_questions: int,
        answers: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> dict[str, Any]:
        submission = {
            "id": str(uuid4()),
            "userId": user_id,
            "quizId": quiz_id,
            "score": score,
            "totalQuestions": total_questions,
            "answers": answers,
            "metadata": metadata,
            "createdAt": _now_iso(),
        }

        with self._lock:
            db = self._read_db()
            submissions = db.get("submissions", [])
            submissions.append(submission)
            db["submissions"] = submissions
            self._write_db(db)

        return submission

    def list_submissions(
        self,
        *,
        user_id: str | None = None,
        quiz_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        with self._lock:
            db = self._read_db()

        submissions = db.get("submissions", [])
        if user_id:
            submissions = [item for item in submissions if item.get("userId") == user_id]
        if quiz_id:
            submissions = [item for item in submissions if item.get("quizId") == quiz_id]

        submissions.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
        return submissions[:limit]

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        with self._lock:
            db = self._read_db()

        for submission in db.get("submissions", []):
            if submission.get("id") == submission_id:
                return submission
        return None
