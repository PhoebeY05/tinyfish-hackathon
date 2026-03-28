from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

DEFAULT_RARITY_SCORE = 55.0

# Higher means rarer.
RARITY_WEIGHTS = {
    "Olive-backed Sunbird": 35.0,
    "Brown-throated Sunbird": 45.0,
    "Yellow-vented Bulbul": 20.0,
    "Asian Koel": 60.0,
    "Collared Kingfisher": 70.0,
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class RarityLeaderboardStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_store()

    def _initialize_store(self) -> None:
        if not self.db_path.exists():
            self._write_db({"entries": []})
            return
        try:
            payload = json.loads(self.db_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("entries", []), list):
                self._write_db({"entries": []})
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            self._write_db({"entries": []})

    def _read_db(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {"entries": []}
        try:
            return json.loads(self.db_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"entries": []}

    def _write_db(self, payload: dict[str, Any]) -> None:
        self.db_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def submit_job_score(
        self,
        *,
        participant_id: str,
        display_name: str,
        job_id: str,
        report: dict[str, Any],
    ) -> dict[str, Any]:
        score_payload = compute_rarity_score(report)
        entry = {
            "id": str(uuid4()),
            "participantId": participant_id,
            "displayName": display_name,
            "jobId": job_id,
            "geography": report.get("geography", "Unknown"),
            "rarityScore": score_payload["rarityScore"],
            "totalImages": score_payload["totalImages"],
            "uniqueSpecies": score_payload["uniqueSpecies"],
            "speciesBreakdown": score_payload["speciesBreakdown"],
            "scoringVersion": "rarity-v1",
            "createdAt": _now_iso(),
        }

        with self._lock:
            db = self._read_db()
            entries = db.get("entries", [])
            # Keep at most one score for each upload job.
            entries = [item for item in entries if item.get("jobId") != job_id]
            entries.append(entry)
            db["entries"] = entries
            self._write_db(db)

        leaderboard = self.get_leaderboard(limit=100000)
        rank = next((i for i, item in enumerate(leaderboard, start=1) if item["id"] == entry["id"]), 1)
        total = max(len(leaderboard), 1)
        percentile = round((1.0 - ((rank - 1) / total)) * 100.0, 2)

        return {"entry": entry, "rank": rank, "totalParticipants": total, "percentile": percentile}

    def get_leaderboard(
        self,
        *,
        limit: int = 50,
        geography: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._lock:
            db = self._read_db()

        entries = db.get("entries", [])
        if geography:
            lowered = geography.lower()
            entries = [entry for entry in entries if str(entry.get("geography", "")).lower() == lowered]

        entries.sort(
            key=lambda item: (
                float(item.get("rarityScore", 0.0)),
                float(item.get("uniqueSpecies", 0)),
                item.get("createdAt", ""),
            ),
            reverse=True,
        )
        return entries[:limit]

    def get_participant_history(self, participant_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            db = self._read_db()
        entries = [entry for entry in db.get("entries", []) if entry.get("participantId") == participant_id]
        entries.sort(key=lambda item: item.get("createdAt", ""), reverse=True)
        return entries[:limit]


def compute_rarity_score(report: dict[str, Any]) -> dict[str, Any]:
    images = report.get("images", [])
    if not images:
        return {"rarityScore": 0.0, "totalImages": 0, "uniqueSpecies": 0, "speciesBreakdown": []}

    contributions: list[float] = []
    species_counter: Counter[str] = Counter()

    for image in images:
        primary = image.get("primary_prediction", {})
        species = str(primary.get("common_name", "Unknown"))
        confidence = float(primary.get("confidence", 0.0))
        rarity_weight = RARITY_WEIGHTS.get(species, DEFAULT_RARITY_SCORE)
        confidence_multiplier = 0.6 + (0.4 * max(0.0, min(confidence, 1.0)))
        contributions.append(rarity_weight * confidence_multiplier)
        species_counter[species] += 1

    average_weighted_rarity = sum(contributions) / len(contributions)
    diversity_bonus = (len(species_counter) / len(images)) * 20.0
    rarity_score = round(min(100.0, average_weighted_rarity + diversity_bonus), 2)

    species_breakdown = [
        {"species": species, "count": count}
        for species, count in species_counter.most_common()
    ]

    return {
        "rarityScore": rarity_score,
        "totalImages": len(images),
        "uniqueSpecies": len(species_counter),
        "speciesBreakdown": species_breakdown,
    }
