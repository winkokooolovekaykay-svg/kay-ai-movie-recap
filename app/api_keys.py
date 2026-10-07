"""API key resolution for AI providers.

Keys can be entered in the web app (Admin -> API Keys) and are stored
server-side in the SQLite settings table. If no key was entered in the UI,
the environment variable is used as a fallback.

Keys are NEVER sent back to the frontend in full -- the admin endpoint only
returns a masked preview (last 4 chars).
"""
from __future__ import annotations
from .config import settings


def gemini_key() -> str:
    from . import db
    return db.get_setting("gemini_api_key", "") or settings.GEMINI_API_KEY


def google_tts_key() -> str:
    from . import db
    return db.get_setting("google_tts_api_key", "") or settings.GOOGLE_TTS_API_KEY


def mask_key(key: str) -> str:
    if not key:
        return ""
    tail = key[-4:] if len(key) > 4 else "****"
    return "••••••••" + tail
