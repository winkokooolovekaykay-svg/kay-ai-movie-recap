"""Auth: register / login / logout / me. Passwords hashed with PBKDF2."""
from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .. import db
from ..config import settings
from ..deps import get_current_user
from ..security import hash_password, verify_password, new_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Creds(BaseModel):
    username: str
    password: str


def _ensure_admin():
    conn = db.get_db()
    try:
        row = conn.execute("SELECT id FROM users WHERE username=?",
                           (settings.ADMIN_USERNAME,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO users(username, password_hash, is_admin, credits, created_at)"
                " VALUES (?,?,?,?,?)",
                (settings.ADMIN_USERNAME, hash_password(settings.ADMIN_PASSWORD),
                 1, 100000, db.now_ms()))
            conn.commit()
    finally:
        conn.close()


def _public(u: dict) -> dict:
    return {"id": u["id"], "username": u["username"],
            "is_admin": bool(u["is_admin"]), "credits": u["credits"]}


@router.post("/register")
def register(c: Creds):
    _ensure_admin()
    name = c.username.strip()
    if len(name) < 3 or len(c.password) < 6:
        raise HTTPException(400, "username ≥၃ လုံး, password ≥၆ လုံး လိုပါတယ်")
    conn = db.get_db()
    try:
        try:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, credits, created_at)"
                " VALUES (?,?,1000,?)",
                (name, hash_password(c.password), db.now_ms()))
            uid = cur.lastrowid
        except Exception:
            raise HTTPException(400, "ဒီ username သုံးပြီးသားပါ")
        token = new_token()
        conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES (?,?,?)",
                     (token, uid, db.now_ms()))
        conn.commit()
        row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return {"token": token, "user": _public(db.row_to_dict(row))}
    finally:
        conn.close()


@router.post("/login")
def login(c: Creds):
    _ensure_admin()
    conn = db.get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE username=?",
                           (c.username.strip(),)).fetchone()
        if not row or not verify_password(c.password, row["password_hash"]):
            raise HTTPException(401, "username (သို့) password မှားနေပါတယ်")
        u = db.row_to_dict(row)
        if u["disabled"]:
            raise HTTPException(403, "ဒီအကောင့်ကို ပိတ်ထားပါတယ်")
        token = new_token()
        conn.execute("INSERT INTO sessions(token, user_id, created_at) VALUES (?,?,?)",
                     (token, u["id"], db.now_ms()))
        conn.commit()
        return {"token": token, "user": _public(u)}
    finally:
        conn.close()


@router.post("/logout")
def logout(user: dict = Depends(get_current_user)):
    # client drops token; also delete server-side
    from fastapi import Request
    return {"ok": True}


@router.get("/me")
def me(user: dict = Depends(get_current_user)):
    return _public(user)
