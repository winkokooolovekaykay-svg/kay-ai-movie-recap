"""Pipeline control: capabilities, start, job status, resume, downloads."""
from __future__ import annotations
import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from .. import db
from .. import jobs as job_engine
from ..api_keys import gemini_key
from ..deps import get_current_user
from ..providers import stt as stt_provider
from ..providers import tts as tts_provider
from ..config import settings

router = APIRouter(prefix="/api", tags=["pipeline"])


@router.get("/capabilities")
def capabilities(user: dict = Depends(get_current_user)):
    return {
        "stt": stt_provider.is_configured(),
        "stt_detail": ("faster-whisper" if _has_fw() else
                       "gemini" if gemini_key() else "none"),
        "ai": bool(gemini_key()),
        "tts": tts_provider.is_configured(),
        "tts_provider": tts_provider.provider_name(),
        "tts_message": "" if tts_provider.is_configured()
                       else tts_provider.requirement_message(),
        "stages": [{"id": s, "label": job_engine.STAGE_MM[s]}
                   for s in job_engine.STAGES],
        "modes": [
            {"id": "translate", "label": "ဘာသာပြန်သာ"},
            {"id": "subtitle", "label": "စာတန်းသာ"},
            {"id": "voice", "label": "မြန်မာအသံသာ"},
            {"id": "voice_subtitle", "label": "အသံ + စာတန်း"},
            {"id": "recap", "label": "Movie Recap အပြည့်"},
            {"id": "short", "label": "Recap အတို (Shorts)"},
        ],
    }


def _has_fw() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def _own_project(pid: int, uid: int) -> dict:
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM projects WHERE id=? AND user_id=?",
                           (pid, uid)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Project မတွေ့ပါ")
    return db.row_to_dict(row)


@router.post("/projects/{pid}/run")
def run_pipeline(pid: int, user: dict = Depends(get_current_user)):
    _own_project(pid, user["id"])
    job_id = job_engine.create_job(pid, user["id"], "pipeline")
    job_engine.launch(job_id)
    return {"job_id": job_id}


@router.get("/jobs/{job_id}")
def job_status(job_id: int, user: dict = Depends(get_current_user)):
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?",
                           (job_id, user["id"])).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Job မတွေ့ပါ")
    j = db.row_to_dict(row)
    j["stage_label"] = job_engine.STAGE_MM.get(j["stage"], j["stage"])
    return j


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: int, user: dict = Depends(get_current_user)):
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id=? AND user_id=?",
                           (job_id, user["id"])).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Job မတွေ့ပါ")
    j = db.row_to_dict(row)
    if j["status"] != "failed":
        raise HTTPException(400, "Failed job မှသာ resume လုပ်နိုင်ပါတယ်")
    new_id = job_engine.create_job(j["project_id"], user["id"], "pipeline")
    job_engine.launch(new_id)
    return {"job_id": new_id}


def _export_file(pid: int, kind: str, uid: int) -> str:
    _own_project(pid, uid)
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT file_path FROM exports WHERE project_id=? AND kind=? "
            "ORDER BY created_at DESC LIMIT 1", (pid, kind)).fetchone()
    finally:
        conn.close()
    if not row or not os.path.exists(row["file_path"]):
        raise HTTPException(404, "ဖိုင်မတွေ့ပါ။ အရင် render လုပ်ပါ။")
    return row["file_path"]


@router.get("/projects/{pid}/download/{kind}")
def download(pid: int, kind: str, user: dict = Depends(get_current_user)):
    if kind not in ("video", "audio", "srt", "script"):
        raise HTTPException(400, "kind မမှန်ပါ")
    path = _export_file(pid, kind, user["id"])
    media = {"video": "video/mp4", "audio": "audio/wav",
             "srt": "text/plain", "script": "text/plain"}[kind]
    return FileResponse(path, media_type=media,
                        filename=f"kay_recap_{pid}.{ {'video':'mp4','audio':'wav','srt':'srt','script':'txt'}[kind] }")


@router.get("/projects/{pid}/video-file")
def video_file(pid: int, user: dict = Depends(get_current_user)):
    p = _own_project(pid, user["id"])
    if not p["video_path"] or not os.path.exists(p["video_path"]):
        raise HTTPException(404, "ဗီဒီယိုမတွေ့ပါ")
    return FileResponse(p["video_path"], media_type="video/mp4")
