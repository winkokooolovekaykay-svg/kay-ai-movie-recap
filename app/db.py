"""SQLite database layer. Schema is intentionally portable so it can later
migrate to PostgreSQL (plain types, no SQLite-only tricks)."""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path
from .config import DB_PATH, settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    disabled INTEGER NOT NULL DEFAULT 0,
    credits REAL NOT NULL DEFAULT 1000,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    source_type TEXT NOT NULL DEFAULT 'upload',
    source_url TEXT NOT NULL DEFAULT '',
    video_path TEXT NOT NULL DEFAULT '',
    thumb_path TEXT NOT NULL DEFAULT '',
    duration_ms INTEGER NOT NULL DEFAULT 0,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    fps REAL NOT NULL DEFAULT 0,
    has_audio INTEGER NOT NULL DEFAULT 0,
    language TEXT NOT NULL DEFAULT 'auto',
    detected_language TEXT NOT NULL DEFAULT '',
    mode TEXT NOT NULL DEFAULT 'dub',
    voice_id TEXT NOT NULL DEFAULT '',
    voice_speed REAL NOT NULL DEFAULT 1.0,
    voice_pitch TEXT NOT NULL DEFAULT 'normal',
    narration_mp3 TEXT NOT NULL DEFAULT '',
    orig_audio_enabled INTEGER NOT NULL DEFAULT 0,
    orig_audio_volume INTEGER NOT NULL DEFAULT 15,
    subtitle_style TEXT NOT NULL DEFAULT 'clean',
    subtitle_position TEXT NOT NULL DEFAULT 'bottom',
    mask_enabled INTEGER NOT NULL DEFAULT 0,
    mask_x INTEGER NOT NULL DEFAULT 0,
    mask_y INTEGER NOT NULL DEFAULT 0,
    mask_w INTEGER NOT NULL DEFAULT 0,
    mask_h INTEGER NOT NULL DEFAULT 0,
    mask_type TEXT NOT NULL DEFAULT 'blur',
    export_preset TEXT NOT NULL DEFAULT 'original',
    export_fps TEXT NOT NULL DEFAULT 'original',
    export_aspect TEXT NOT NULL DEFAULT 'original',
    export_quality TEXT NOT NULL DEFAULT 'balanced',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    idx INTEGER NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    original_text TEXT NOT NULL DEFAULT '',
    burmese_text TEXT NOT NULL DEFAULT '',
    voice_text TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'pipeline',
    stage TEXT NOT NULL DEFAULT 'queued',
    stage_index INTEGER NOT NULL DEFAULT 0,
    progress INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'queued',
    error TEXT NOT NULL DEFAULT '',
    result_path TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'video',
    file_path TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""

DEFAULT_SETTINGS = {
    "credit_price_video_per_min": "10",
    "credit_price_voice_per_min": "5",
    "credit_price_recap_per_min": "15",
    "ai_model": settings.GEMINI_MODEL,
    "tts_provider": settings.TTS_PROVIDER,
    "max_upload_mb": str(settings.MAX_UPLOAD_SIZE_MB),
    "max_video_min": str(settings.MAX_VIDEO_DURATION_MIN),
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_db() -> sqlite3.Connection:
    return _connect()


def init_db() -> None:
    conn = _connect()
    try:
        conn.executescript(SCHEMA)
        # guarded migration for DBs created before narration_mp3 existed
        try:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)")]
            if "narration_mp3" not in cols:
                conn.execute(
                    "ALTER TABLE projects ADD COLUMN narration_mp3 TEXT NOT NULL DEFAULT ''")
        except Exception:
            pass
        for k, v in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)", (k, v)
            )
        conn.commit()
    finally:
        conn.close()


def now_ms() -> int:
    return int(time.time() * 1000)


def get_setting(key: str, default: str = "") -> str:
    conn = _connect()
    try:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default
    finally:
        conn.close()


def set_setting(key: str, value: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row) -> dict:
    return dict(row) if row is not None else {}
