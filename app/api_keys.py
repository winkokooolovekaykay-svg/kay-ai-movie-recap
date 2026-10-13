"""API key resolution for AI providers.

The environment variable takes precedence when set. This matters on
hosts with ephemeral disks (e.g. SnapDeploy): a key entered in the web
app (Admin -> API Keys) is stored in the SQLite settings table and is
lost on container sleep/restart, while an env var survives. Env-first
also means a stale or wrong app-stored key can never override a correct
env var. The app-stored key is used only when no env var is set.

Keys are NEVER sent back to the frontend in full -- the admin endpoint only
returns a masked preview (last 4 chars).
"""
from __future__ import annotations
from .config import settings


def gemini_key() -> str:
    from . import db
    return settings.GEMINI_API_KEY or db.get_setting("gemini_api_key", "")


def google_tts_key() -> str:
    from . import db
    return settings.GOOGLE_TTS_API_KEY or db.get_setting("google_tts_api_key", "")


def mask_key(key: str) -> str:
    if not key:
        return ""
    tail = key[-4:] if len(key) > 4 else "****"
    return "••••••••" + tail
