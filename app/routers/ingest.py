"""Ingest: file upload only (URL import removed for hosting AUP compliance)."""
from __future__ import annotations
import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from .. import db
from ..config import UPLOAD_DIR, THUMB_DIR, settings
from ..deps import get_current_user
from ..services import ingest as ing
from ..services import analyze as analyze_svc
from ..services import audio as audio_svc

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _create_project(user_id: int, name: str, source_type: str, source_url: str,
                    video_path: str) -> dict:
    info = analyze_svc.analyze(video_path)
    max_min = int(db.get_setting("max_video_min",
                                 str(settings.MAX_VIDEO_DURATION_MIN)))
    if info["duration_ms"] > max_min * 60000:
        os.unlink(video_path)
        raise HTTPException(
            400, f"ဗီဒီယိုရှည်လွန်းပါတယ်။ {max_min} မိနစ်အောက်သုံးပါ။")
    thumb = str(THUMB_DIR / f"{uuid.uuid4().hex}.jpg")
    audio_svc.make_thumbnail(video_path, thumb)
    conn = db.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO projects(user_id, name, source_type, source_url, video_path,"
            " thumb_path, duration_ms, width, height, fps, has_audio, status,"
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (user_id, name[:120], source_type, source_url, video_path, thumb,
             info["duration_ms"], info["width"], info["height"], info["fps"],
             int(info["has_audio"]), "draft", db.now_ms(), db.now_ms()))
        pid = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
        return db.row_to_dict(row)
    finally:
        conn.close()


@router.post("/upload")
async def upload_video(file: UploadFile = File(...),
                       user: dict = Depends(get_current_user)):
    try:
        ext = ing.validate_extension(file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))
    max_mb = int(db.get_setting("max_upload_mb",
                                str(settings.MAX_UPLOAD_SIZE_MB)))
    dest = str(UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}")
    try:
        ing.save_upload_stream(file.file, dest, max_mb * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(400, str(e))
    try:
        return _create_project(user["id"], os.path.splitext(file.filename or "video")[0],
                               "upload", "", dest)
    except HTTPException:
        raise
    except Exception as e:
        if os.path.exists(dest):
            os.unlink(dest)
        raise HTTPException(400, f"ဗီဒီယိုဖိုင်ဖတ်၍မရပါ: {e}")
