"""Speech-to-text abstraction.

Priority:
  1. faster-whisper (local, optional pip dependency)
  2. Gemini multimodal (needs GEMINI_API_KEY, chunks audio inline)
Otherwise raises ProviderUnavailable with a Burmese message — never fakes.
"""
from __future__ import annotations
import base64
import math
import os
import subprocess
import tempfile
from . import ProviderUnavailable
from . import ai as gemini
from ..api_keys import gemini_key
from ..config import settings


def is_configured() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return bool(gemini_key())


def _chunk_wav(src: str, chunk_sec: int = 60) -> list[tuple[str, float]]:
    """Split wav into chunks; returns [(path, offset_sec)]."""
    tmp = tempfile.mkdtemp(prefix="stt_")
    # get duration
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", src],
        capture_output=True, text=True)
    try:
        total = float(probe.stdout.strip())
    except Exception:
        total = 0
    chunks = []
    if total <= 0:
        return chunks
    n = math.ceil(total / chunk_sec)
    for i in range(n):
        out = os.path.join(tmp, f"c{i:03d}.wav")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-ss", str(i * chunk_sec),
             "-t", str(chunk_sec), "-i", src, "-ar", "16000", "-ac", "1", out],
            capture_output=True)
        if r.returncode == 0 and os.path.exists(out):
            chunks.append((out, i * chunk_sec))
    return chunks


def transcribe(wav_path: str, progress_cb=None) -> list[dict]:
    """Returns [{start_ms, end_ms, text}]."""
    try:
        import faster_whisper
        return _via_whisper(wav_path, progress_cb)
    except ImportError:
        pass
    if gemini_key():
        return _via_gemini(wav_path, progress_cb)
    raise ProviderUnavailable(
        "အသံစာသားထုတ်ဖို့ faster-whisper (သို့) Gemini API key လိုအပ်ပါတယ်။ "
        "Admin → 🔑 API Keys မှာ key ထည့်ပါ။"
    )


def _via_whisper(wav_path: str, progress_cb=None) -> list[dict]:
    from faster_whisper import WhisperModel
    model = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(wav_path, vad_filter=True)
    out = []
    for s in segments:
        out.append({
            "start_ms": int(s.start * 1000),
            "end_ms": int(s.end * 1000),
            "text": s.text.strip(),
        })
        if progress_cb:
            progress_cb()
    return [s for s in out if s["text"]]


PROMPT = (
    "Transcribe the speech in this audio clip. Output ONLY lines in this exact format, "
    "one per spoken sentence:\n[MM:SS.mmm-MM:SS.mmm] sentence text\n"
    "Timestamps are relative to the START of this clip. Do not add commentary."
)


def _via_gemini(wav_path: str, progress_cb=None) -> list[dict]:
    chunks = _chunk_wav(wav_path)
    if not chunks:
        raise ProviderUnavailable("အသံဖိုင်ဖတ်၍မရပါ။")
    out: list[dict] = []
    total = len(chunks)
    for i, (path, offset) in enumerate(chunks):
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        text = gemini.generate_with_audio(PROMPT, b64)
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("["):
                continue
            try:
                ts, sent = line[1:].split("]", 1)
                a, b = ts.split("-")
                out.append({
                    "start_ms": int(_ts(a) * 1000 + offset * 1000),
                    "end_ms": int(_ts(b) * 1000 + offset * 1000),
                    "text": sent.strip(),
                })
            except Exception:
                continue
        if progress_cb:
            progress_cb((i + 1) / total)
    return [s for s in out if s["text"]]


def _ts(t: str) -> float:
    t = t.strip()
    parts = t.split(":")
    sec = float(parts[-1])
    mult = 60
    for p in reversed(parts[:-1]):
        sec += float(p) * mult
        mult *= 60
    return sec
