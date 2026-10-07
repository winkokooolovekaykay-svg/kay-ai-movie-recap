"""Voice Studio: list voices, preview a voice with sample text."""
from __future__ import annotations
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from ..deps import get_current_user
from ..providers import tts as tts_provider
from ..providers import ProviderUnavailable

router = APIRouter(prefix="/api/tts", tags=["tts"])


@router.get("/voices")
def voices(user: dict = Depends(get_current_user)):
    try:
        return {"configured": True, "voices": tts_provider.list_voices()}
    except ProviderUnavailable as e:
        return {"configured": False, "voices": [], "message": str(e)}


class PreviewBody(BaseModel):
    text: str = "ဒီနေ့ပြောပြမယ့်ဇာတ်လမ်းကတော့..."
    voice_id: str = ""
    speed: float = 1.0
    pitch: str = "normal"


@router.post("/preview")
def preview(body: PreviewBody, user: dict = Depends(get_current_user)):
    if not body.text.strip():
        raise HTTPException(400, "စာသားထည့်ပါ")
    try:
        out = os.path.join(tempfile.gettempdir(),
                           f"kay_preview_{user['id']}.wav")
        tts_provider.synthesize(body.text[:300], body.voice_id,
                                speed=body.speed, pitch=body.pitch, out_path=out)
        return FileResponse(out, media_type="audio/wav", filename="preview.wav")
    except ProviderUnavailable as e:
        raise HTTPException(400, str(e))
