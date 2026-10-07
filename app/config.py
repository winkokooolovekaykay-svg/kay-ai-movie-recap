"""Centralized configuration. Everything comes from environment variables."""
from __future__ import annotations
import os
from pathlib import Path


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


class Settings:
    # AI
    GEMINI_API_KEY: str = _get("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = _get("GEMINI_MODEL", "gemini-3.5-flash")
    # TTS
    TTS_PROVIDER: str = _get("TTS_PROVIDER", "none").lower()
    GOOGLE_TTS_API_KEY: str = _get("GOOGLE_TTS_API_KEY", "")
    TTS_DEFAULT_VOICE: str = _get("TTS_DEFAULT_VOICE", "")
    # Local STT
    WHISPER_MODEL: str = _get("WHISPER_MODEL", "small")
    # Limits
    MAX_UPLOAD_SIZE_MB: int = _get_int("MAX_UPLOAD_SIZE_MB", 500)
    MAX_VIDEO_DURATION_MIN: int = _get_int("MAX_VIDEO_DURATION_MIN", 120)
    # Paths
    DATA_DIR: Path = Path(_get("DATA_DIR", "./data")).resolve()
    # First admin
    ADMIN_USERNAME: str = _get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = _get("ADMIN_PASSWORD", "changeme123")


settings = Settings()

UPLOAD_DIR = settings.DATA_DIR / "uploads"
PROJECT_DIR = settings.DATA_DIR / "projects"
EXPORT_DIR = settings.DATA_DIR / "exports"
THUMB_DIR = settings.DATA_DIR / "thumbs"
TMP_DIR = settings.DATA_DIR / "tmp"
for d in (UPLOAD_DIR, PROJECT_DIR, EXPORT_DIR, THUMB_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

DB_PATH = settings.DATA_DIR / "kay.db"
