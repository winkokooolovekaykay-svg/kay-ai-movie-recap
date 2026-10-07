"""Admin panel: users, jobs, errors, settings (pricing, models, limits)."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .. import db
from ..api_keys import gemini_key, google_tts_key, mask_key
from ..config import settings as env_settings
from ..deps import get_admin_user
from ..security import hash_password

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def users(admin: dict = Depends(get_admin_user)):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT id, username, is_admin, disabled, credits, created_at FROM users "
            "ORDER BY id").fetchall()
        return [db.row_to_dict(r) for r in rows]
    finally:
        conn.close()


class CreditBody(BaseModel):
    amount: float


@router.post("/users/{uid}/credits")
def add_credits(uid: int, body: CreditBody, admin: dict = Depends(get_admin_user)):
    conn = db.get_db()
    try:
        conn.execute("UPDATE users SET credits=credits+? WHERE id=?",
                     (body.amount, uid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/users/{uid}/disable")
def disable_user(uid: int, admin: dict = Depends(get_admin_user)):
    if uid == admin["id"]:
        raise HTTPException(400, "ကိုယ့်ကိုယ်ကို ပိတ်၍မရပါ")
    conn = db.get_db()
    try:
        conn.execute("UPDATE users SET disabled=1 WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/users/{uid}/enable")
def enable_user(uid: int, admin: dict = Depends(get_admin_user)):
    conn = db.get_db()
    try:
        conn.execute("UPDATE users SET disabled=0 WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.get("/jobs")
def all_jobs(admin: dict = Depends(get_admin_user)):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT j.*, u.username FROM jobs j LEFT JOIN users u ON u.id=j.user_id "
            "ORDER BY j.id DESC LIMIT 100").fetchall()
        return [db.row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/errors")
def errors(admin: dict = Depends(get_admin_user)):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT j.id, j.stage, j.error, j.created_at, u.username FROM jobs j "
            "LEFT JOIN users u ON u.id=j.user_id "
            "WHERE j.status='failed' ORDER BY j.id DESC LIMIT 100").fetchall()
        return [db.row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/settings")
def get_settings(admin: dict = Depends(get_admin_user)):
    # API keys are never exposed here -- they have their own masked endpoint.
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key NOT IN "
            "('gemini_api_key', 'google_tts_api_key')").fetchall()
        return {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()


class SettingsBody(BaseModel):
    data: dict


@router.patch("/settings")
def patch_settings(body: SettingsBody, admin: dict = Depends(get_admin_user)):
    allowed = {"credit_price_video_per_min", "credit_price_voice_per_min",
               "credit_price_recap_per_min", "ai_model", "tts_provider",
               "max_upload_mb", "max_video_min"}
    for k, v in body.data.items():
        if k in allowed:
            db.set_setting(k, str(v))
    return {"ok": True}


class ApiKeysBody(BaseModel):
    gemini_api_key: str = ""
    google_tts_api_key: str = ""


@router.get("/api-keys")
def get_api_keys(admin: dict = Depends(get_admin_user)):
    """Return masked key status only -- full keys are never sent to the client."""
    gk, tk = gemini_key(), google_tts_key()
    return {
        "gemini": {
            "configured": bool(gk),
            "masked": mask_key(gk),
            "source": ("app" if db.get_setting("gemini_api_key", "") else
                       "env" if env_settings.GEMINI_API_KEY else "none"),
        },
        "google_tts": {
            "configured": bool(tk),
            "masked": mask_key(tk),
            "source": ("app" if db.get_setting("google_tts_api_key", "") else
                       "env" if env_settings.GOOGLE_TTS_API_KEY else "none"),
        },
    }


@router.post("/api-keys")
def save_api_keys(body: ApiKeysBody, admin: dict = Depends(get_admin_user)):
    """Save keys server-side. Empty string clears the app-stored key
    (falls back to the environment variable)."""
    db.set_setting("gemini_api_key", body.gemini_api_key.strip())
    db.set_setting("google_tts_api_key", body.google_tts_api_key.strip())
    return {"ok": True}
