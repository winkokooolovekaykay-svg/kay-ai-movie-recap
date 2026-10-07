"""Projects CRUD + settings, duplicate, delete, auto-save."""
from __future__ import annotations
import os
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from .. import db
from ..config import PROJECT_DIR
from ..deps import get_current_user
from ..services import audio as audio_svc
from ..services import ingest as ing

router = APIRouter(prefix="/api/projects", tags=["projects"])

UPDATABLE = {"name", "language", "mode", "voice_id", "voice_speed", "voice_pitch",
             "orig_audio_enabled", "orig_audio_volume", "subtitle_style",
             "subtitle_position", "mask_enabled", "mask_x", "mask_y", "mask_w",
             "mask_h", "mask_type", "export_preset", "export_fps",
             "export_aspect", "export_quality"}


class Patch(BaseModel):
    data: dict


def _one(pid: int, uid: int) -> dict:
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT * FROM projects WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Project မတွေ့ပါ")
    return db.row_to_dict(row)


@router.get("")
def list_projects(user: dict = Depends(get_current_user)):
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM projects WHERE user_id=? ORDER BY updated_at DESC",
            (user["id"],)).fetchall()
        return [db.row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/{pid}")
def get_project(pid: int, user: dict = Depends(get_current_user)):
    p = _one(pid, user["id"])
    conn = db.get_db()
    try:
        segs = conn.execute(
            "SELECT * FROM segments WHERE project_id=? ORDER BY idx",
            (pid,)).fetchall()
        exps = conn.execute(
            "SELECT * FROM exports WHERE project_id=? ORDER BY created_at DESC",
            (pid,)).fetchall()
        jobs = conn.execute(
            "SELECT * FROM jobs WHERE project_id=? ORDER BY id DESC LIMIT 5",
            (pid,)).fetchall()
    finally:
        conn.close()
    p["segments"] = [db.row_to_dict(r) for r in segs]
    p["exports"] = [db.row_to_dict(r) for r in exps]
    p["recent_jobs"] = [db.row_to_dict(r) for r in jobs]
    return p


@router.patch("/{pid}")
def patch_project(pid: int, body: Patch, user: dict = Depends(get_current_user)):
    _one(pid, user["id"])
    data = {k: v for k, v in body.data.items() if k in UPDATABLE}
    if not data:
        return {"ok": True}
    conn = db.get_db()
    try:
        sets = ", ".join(f"{k}=?" for k in data) + ", updated_at=?"
        conn.execute(f"UPDATE projects SET {sets} WHERE id=?",
                     list(data.values()) + [db.now_ms(), pid])
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/{pid}/duplicate")
def duplicate(pid: int, user: dict = Depends(get_current_user)):
    p = _one(pid, user["id"])
    conn = db.get_db()
    try:
        cols = [c for c in p.keys() if c not in ("id", "created_at", "updated_at")]
        vals = [p[c] for c in cols]
        cols2 = cols[:]
        i = cols2.index("name")
        vals[i] = str(vals[i]) + " (copy)"
        i2 = cols2.index("status")
        vals[i2] = "draft"
        cur = conn.execute(
            f"INSERT INTO projects({','.join(cols2)}, created_at, updated_at) "
            f"VALUES ({','.join('?'*len(cols2))},?,?)",
            vals + [db.now_ms(), db.now_ms()])
        nid = cur.lastrowid
        segs = conn.execute("SELECT * FROM segments WHERE project_id=? ORDER BY idx",
                            (pid,)).fetchall()
        for s in segs:
            d = db.row_to_dict(s)
            conn.execute(
                "INSERT INTO segments(project_id, idx, start_ms, end_ms, original_text,"
                " burmese_text, voice_text, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (nid, d["idx"], d["start_ms"], d["end_ms"], d["original_text"],
                 d["burmese_text"], d["voice_text"], db.now_ms()))
        conn.commit()
        return {"id": nid}
    finally:
        conn.close()


@router.delete("/{pid}")
def delete_project(pid: int, user: dict = Depends(get_current_user)):
    import os
    p = _one(pid, user["id"])
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM segments WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM jobs WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM exports WHERE project_id=?", (pid,))
        conn.execute("DELETE FROM projects WHERE id=?", (pid,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


NARRATION_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac"}


@router.post("/{pid}/narration")
async def upload_narration(pid: int, file: UploadFile = File(...),
                           user: dict = Depends(get_current_user)):
    """Upload a self-made narration audio (e.g. from Lovevoice) that the
    pipeline will mux as the voiceover instead of Google TTS."""
    p = _one(pid, user["id"])
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in NARRATION_EXTS:
        raise HTTPException(
            400, "အသံဖိုင်အမျိုးအစားမမှန်ပါ။ MP3 / WAV / M4A သာရပါတယ်။")
    workdir = PROJECT_DIR / str(pid)
    workdir.mkdir(parents=True, exist_ok=True)
    dest = str(workdir / f"narration_upload{ext}")
    try:
        ing.save_upload_stream(file.file, dest, 100 * 1024 * 1024)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if not audio_svc.has_audio_stream(dest):
        if os.path.exists(dest):
            os.unlink(dest)
        raise HTTPException(
            400, "အသံလမ်းကြောင်းမပါတဲ့ ဖိုင်ပါ။ MP3 အသံဖိုင်မှန်ကန်ရဲ့လား စစ်ပါ။")
    old = p.get("narration_mp3") or ""
    if old and old != dest and os.path.exists(old):
        os.unlink(old)
    conn = db.get_db()
    try:
        conn.execute("UPDATE projects SET narration_mp3=?, updated_at=? WHERE id=?",
                     (dest, db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "narration_mp3": dest,
            "duration_ms": audio_svc.wav_duration_ms(dest)}


@router.delete("/{pid}/narration")
def delete_narration(pid: int, user: dict = Depends(get_current_user)):
    p = _one(pid, user["id"])
    old = p.get("narration_mp3") or ""
    if old and os.path.exists(old):
        try:
            os.unlink(old)
        except OSError:
            pass
    conn = db.get_db()
    try:
        conn.execute("UPDATE projects SET narration_mp3='', updated_at=? WHERE id=?",
                     (db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}
