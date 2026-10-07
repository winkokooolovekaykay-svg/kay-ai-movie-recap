"""Burmese TTS provider abstraction.

Recommended provider: Google Cloud Text-to-Speech (has my-MM Burmese voices).
Enter the key in the web app: Admin -> 🔑 API Keys (or set
TTS_PROVIDER=google and GOOGLE_TTS_API_KEY in .env).

If no provider is configured, every call raises ProviderUnavailable with a
Burmese message — the UI shows "API key လိုအပ်ပါတယ်" and never fakes audio.
"""
from __future__ import annotations
import json
import urllib.request
from . import ProviderUnavailable
from ..config import settings
from ..api_keys import google_tts_key


def provider_name() -> str:
    from ..db import get_setting
    return get_setting("tts_provider", settings.TTS_PROVIDER) or "none"


def is_configured() -> bool:
    p = provider_name()
    if p == "google":
        return bool(google_tts_key())
    return False


def requirement_message() -> str:
    return (
        "မြန်မာအသံထုတ်ဖို့ TTS API key လိုအပ်ပါတယ်။ "
        "Admin → 🔑 API Keys မှာ Google Cloud Text-to-Speech key ထည့်ပါ "
        "(my-MM အသံများ)။"
    )


# ---- Google Cloud TTS -------------------------------------------------------

def _gkey() -> str:
    key = google_tts_key()
    if not key:
        raise ProviderUnavailable(requirement_message())
    return key


def google_list_voices() -> list[dict]:
    """Returns [{id, name, gender}] filtered to Burmese (my-MM), fallback all."""
    key = _gkey()
    url = f"https://texttospeech.googleapis.com/v1/voices?key={key}&languageCode=my-MM"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        raise ProviderUnavailable(f"Google TTS ဆက်သွယ်၍မရပါ: {e}")
    voices = []
    for v in data.get("voices", []):
        langs = v.get("languageCodes", [])
        if not any(l.startswith("my") for l in langs):
            continue
        vid = v["name"]
        gender = v.get("ssmlGender", "NEUTRAL").capitalize()
        voices.append({"id": vid, "name": f"{vid} ({gender})", "gender": gender,
                       "lang": langs[0]})
    return voices


def list_voices() -> list[dict]:
    p = provider_name()
    if p == "google":
        return google_list_voices()
    raise ProviderUnavailable(requirement_message())


def synthesize(text: str, voice_id: str, *, speed: float = 1.0,
               pitch: str = "normal", out_path: str = "") -> str:
    """Synthesize Burmese text -> wav file. Returns out_path."""
    p = provider_name()
    if p == "google":
        return _google_synthesize(text, voice_id, speed, pitch, out_path)
    raise ProviderUnavailable(requirement_message())


def _google_synthesize(text: str, voice_id: str, speed: float, pitch: str,
                       out_path: str) -> str:
    key = _gkey()
    if not voice_id:
        voice_id = settings.TTS_DEFAULT_VOICE or "my-MM-Standard-A"
    pitch_map = {"low": -4.0, "normal": 0.0, "high": 4.0}
    lang = "-".join(voice_id.split("-")[:2]) if "-" in voice_id else "my-MM"
    payload = {
        "input": {"text": text},
        "voice": {"languageCode": lang, "name": voice_id},
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "speakingRate": max(0.25, min(4.0, speed)),
            "pitch": pitch_map.get(pitch, 0.0),
        },
    }
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        raise ProviderUnavailable(f"အသံထုတ်၍မရပါ: {e}")
    import base64
    audio = base64.b64decode(data["audioContent"])
    # convert to 44.1k mono wav via ffmpeg for consistent mixing
    import subprocess, tempfile, os
    tmp = tempfile.mktemp(suffix=".raw.wav")
    with open(tmp, "wb") as f:
        f.write(audio)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", tmp, "-ar", "44100", "-ac", "1",
         out_path],
        capture_output=True)
    os.unlink(tmp)
    if r.returncode != 0 or not os.path.exists(out_path):
        raise ProviderUnavailable("အသံဖိုင်ပြောင်း၍မရပါ။")
    return out_path
