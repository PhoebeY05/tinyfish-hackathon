from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    port: int
    upload_dir: Path
    report_dir: Path
    quiz_db_path: Path
    rarity_leaderboard_db_path: Path
    enable_live_lookups: bool
    tinyfish_api_key: str
    tinyfish_base_url: str
    tinyfish_default_search_url: str
    enable_openai_classification: bool
    openai_api_key: str
    openai_model: str


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.lower() == "true"


def load_settings() -> Settings:
    enable_live_lookups = _parse_bool(os.getenv("ENABLE_LIVE_LOOKUPS"), False)
    enable_openai_classification = _parse_bool(os.getenv("ENABLE_OPENAI_CLASSIFICATION"), False)
    
    settings = Settings(
        port=int(os.getenv("PORT", "3000")),
        upload_dir=Path(os.getenv("UPLOAD_DIR", "data/uploads")).resolve(),
        report_dir=Path(os.getenv("REPORT_DIR", "data/reports")).resolve(),
        quiz_db_path=Path(os.getenv("QUIZ_DB_PATH", "data/quiz/user_quiz_data.json")).resolve(),
        rarity_leaderboard_db_path=Path(
            os.getenv("RARITY_LEADERBOARD_DB_PATH", "data/leaderboard/rarity_leaderboard.json")
        ).resolve(),
        enable_live_lookups=enable_live_lookups,
        tinyfish_api_key=os.getenv("TINYFISH_API_KEY", ""),
        tinyfish_base_url=os.getenv("TINYFISH_BASE_URL", "https://api.tinyfish.ai"),
        tinyfish_default_search_url=os.getenv("TINYFISH_DEFAULT_SEARCH_URL", "https://ebird.org/region/SG"),
        enable_openai_classification=enable_openai_classification,
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
    )

    if settings.enable_live_lookups and not settings.tinyfish_api_key:
        raise RuntimeError(
            "ENABLE_LIVE_LOOKUPS=true requires TINYFISH_API_KEY. Startup blocked by fail-fast config validation."
        )
    
    if settings.enable_openai_classification and not settings.openai_api_key:
        raise RuntimeError(
            "ENABLE_OPENAI_CLASSIFICATION=true requires OPENAI_API_KEY. Startup blocked by fail-fast config validation."
        )

    return settings
