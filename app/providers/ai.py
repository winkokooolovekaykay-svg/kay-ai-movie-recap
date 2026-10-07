"""Gemini client over REST (no heavy SDK needed). Centralized model config."""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from . import ProviderUnavailable
from ..config import settings
from ..api_keys import gemini_key

# Free-tier keys hit 429/503 under burst load and occasional transient 400s;
# back off and retry. A persistently malformed request still fails honestly
# after all attempts — never faked, never retried forever.
_RETRYABLE = {400, 429, 503}
_RETRY_DELAYS = (8, 20, 45)  # seconds between attempts


def _post(url: str, payload: dict, timeout: int) -> dict:
    # Calibrate safety filters for film-recap localization: the source is
    # existing movie narration being translated, not new harmful content.
    # BLOCK_ONLY_HIGH keeps strong protection while allowing legitimate
    # drama/romance plot description through.
    payload.setdefault("safetySettings", [
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
    ])
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    last_err: Exception | None = None
    for attempt in range(len(_RETRY_DELAYS) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in _RETRYABLE and attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            if attempt < len(_RETRY_DELAYS):
                time.sleep(_RETRY_DELAYS[attempt])
                continue
            raise
    raise last_err  # pragma: no cover - loop always raises first


def _model() -> str:
    # Admin panel can override the model at runtime.
    from ..db import get_setting
    return get_setting("ai_model", settings.GEMINI_MODEL) or settings.GEMINI_MODEL


def _key() -> str:
    key = gemini_key()
    if not key:
        raise ProviderUnavailable(
            "Gemini API key မရှိသေးပါ။ Admin → 🔑 API Keys မှာ key ထည့်ပြီးမှ သုံးနိုင်ပါမယ်။"
        )
    return key


def generate_text(prompt: str, *, system: str = "", timeout: int = 120) -> str:
    """Single-turn text generation. Raises ProviderUnavailable on any failure."""
    key = _key()
    model = _model()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={key}"
    )
    parts = []
    if system:
        parts.append({"text": f"[System instruction]\n{system}\n\n{prompt}"})
    else:
        parts.append({"text": prompt})
    body = {"contents": [{"parts": parts}]}
    try:
        data = _post(url, body, timeout)
    except Exception as e:
        raise ProviderUnavailable(f"Gemini ဆက်သွယ်၍မရပါ: {e}")
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        raise ProviderUnavailable("Gemini က အဖြေပြန်မပေးပါ။ နောက်မှထပ်ကြိုးစားပါ။")


def generate_with_audio(prompt: str, audio_b64: str, mime: str = "audio/wav",
                        timeout: int = 180) -> str:
    """Multimodal transcription helper: audio + instruction -> text."""
    key = _key()
    model = _model()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={key}"
    )
    body = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": mime, "data": audio_b64}},
                {"text": prompt},
            ]
        }]
    }
    try:
        data = _post(url, body, timeout)
    except Exception as e:
        raise ProviderUnavailable(f"Gemini ဆက်သွယ်၍မရပါ: {e}")
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        raise ProviderUnavailable("Gemini က အသံစာသားပြန်မပေးပါ။")
