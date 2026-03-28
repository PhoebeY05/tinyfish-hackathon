from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    port: int
    upload_dir: Path
    report_dir: Path
    enable_live_lookups: bool
    tinyfish_api_key: str
    tinyfish_base_url: str


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.lower() == "true"


def load_settings() -> Settings:
    enable_live_lookups = _parse_bool(os.getenv("ENABLE_LIVE_LOOKUPS"), False)
    settings = Settings(
        port=int(os.getenv("PORT", "3000")),
        upload_dir=Path(os.getenv("UPLOAD_DIR", "data/uploads")).resolve(),
        report_dir=Path(os.getenv("REPORT_DIR", "data/reports")).resolve(),
        enable_live_lookups=enable_live_lookups,
        tinyfish_api_key=os.getenv("TINYFISH_API_KEY", ""),
        tinyfish_base_url=os.getenv("TINYFISH_BASE_URL", "https://api.tinyfish.ai"),
    )

    if settings.enable_live_lookups and not settings.tinyfish_api_key:
        raise RuntimeError(
            "ENABLE_LIVE_LOOKUPS=true requires TINYFISH_API_KEY. Startup blocked by fail-fast config validation."
        )

    return settings
