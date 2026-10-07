"""Timeline script editor: list / update / add / delete / auto-fix timing."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .. import db
from ..deps import get_current_user
from ..services import subtitle as sub_svc

router = APIRouter(prefix="/api/projects", tags=["segments"])


def _own(pid: int, uid: int):
    conn = db.get_db()
    try:
        row = conn.execute(
            "SELECT id FROM projects WHERE id=? AND user_id=?", (pid, uid)).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(404, "Project မတွေ့ပါ")


class SegUpdate(BaseModel):
    start_ms: int | None = None
    end_ms: int | None = None
    original_text: str | None = None
    burmese_text: str | None = None
    voice_text: str | None = None


class SegCreate(BaseModel):
    start_ms: int
    end_ms: int
    original_text: str = ""
    burmese_text: str = ""
    voice_text: str = ""


@router.get("/{pid}/segments")
def list_segments(pid: int, user: dict = Depends(get_current_user)):
    _own(pid, user["id"])
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM segments WHERE project_id=? ORDER BY idx", (pid,)).fetchall()
        return [db.row_to_dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/{pid}/segments")
def add_segment(pid: int, body: SegCreate, user: dict = Depends(get_current_user)):
    _own(pid, user["id"])
    conn = db.get_db()
    try:
        row = conn.execute("SELECT COALESCE(MAX(idx),-1)+1 AS n FROM segments "
                           "WHERE project_id=?", (pid,)).fetchone()
        n = row["n"]
        cur = conn.execute(
            "INSERT INTO segments(project_id, idx, start_ms, end_ms, original_text,"
            " burmese_text, voice_text, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (pid, n, body.start_ms, body.end_ms, body.original_text,
             body.burmese_text, body.voice_text or body.burmese_text, db.now_ms()))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now_ms(), pid))
        conn.commit()
        return {"id": cur.lastrowid}
    finally:
        conn.close()


@router.patch("/{pid}/segments/{sid}")
def update_segment(pid: int, sid: int, body: SegUpdate,
                   user: dict = Depends(get_current_user)):
    _own(pid, user["id"])
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        return {"ok": True}
    conn = db.get_db()
    try:
        sets = ", ".join(f"{k}=?" for k in data)
        conn.execute(f"UPDATE segments SET {sets} WHERE id=? AND project_id=?",
                     list(data.values()) + [sid, pid])
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.delete("/{pid}/segments/{sid}")
def delete_segment(pid: int, sid: int, user: dict = Depends(get_current_user)):
    _own(pid, user["id"])
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM segments WHERE id=? AND project_id=?", (sid, pid))
        # reindex
        rows = conn.execute("SELECT id FROM segments WHERE project_id=? ORDER BY idx",
                            (pid,)).fetchall()
        for i, r in enumerate(rows):
            conn.execute("UPDATE segments SET idx=? WHERE id=?", (i, r["id"]))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


@router.post("/{pid}/segments/autofix")
def autofix(pid: int, user: dict = Depends(get_current_user)):
    """Smart timing: fix overlaps, clamp durations, reindex."""
    _own(pid, user["id"])
    conn = db.get_db()
    try:
        rows = conn.execute("SELECT * FROM segments WHERE project_id=? ORDER BY start_ms",
                            (pid,)).fetchall()
        segs = [db.row_to_dict(r) for r in rows]
        fixed = sub_svc.fix_timing(segs)
        for i, s in enumerate(fixed):
            conn.execute("UPDATE segments SET idx=?, start_ms=?, end_ms=? WHERE id=?",
                         (i, s["start_ms"], s["end_ms"], s["id"]))
        conn.commit()
        return {"fixed": len(fixed)}
    finally:
        conn.close()
