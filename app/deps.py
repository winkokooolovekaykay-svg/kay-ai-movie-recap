"""Auth dependencies: current user / admin from Bearer token."""
from __future__ import annotations
from fastapi import Depends, HTTPException, Request
from .db import get_db, row_to_dict


def _token_from_request(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get("kay_token")


def get_current_user(request: Request) -> dict:
    token = _token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="အကောင့်ဝင်ရန်လိုအပ်ပါတယ်")
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id "
            "WHERE s.token=?",
            (token,),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Session သက်တမ်းကုန်သွားပါပြီ")
    user = row_to_dict(row)
    if user.get("disabled"):
        raise HTTPException(status_code=403, detail="ဒီအကောင့်ကို ပိတ်ထားပါတယ်")
    return user


def get_admin_user(user: dict = Depends(get_current_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin မှသာ ဝင်နိုင်ပါတယ်")
    return user


def optional_user(request: Request) -> dict | None:
    try:
        return get_current_user(request)
    except HTTPException:
        return None
