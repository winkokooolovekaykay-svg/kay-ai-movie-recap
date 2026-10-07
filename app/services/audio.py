"""ffmpeg audio helpers: extraction, thumbnail, voice-track building, mixing."""
from __future__ import annotations
import os
import subprocess


def extract_wav(video_path: str, out_wav: str) -> str:
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video_path,
         "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", out_wav],
        capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError("အသံထုတ်ယူ၍မရပါ: " + (r.stderr or "")[:300])
    return out_wav


def extract_audio_track(video_path: str, out_path: str) -> str:
    """Full-quality audio track for final mixing (wav)."""
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video_path,
         "-vn", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", out_path],
        capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("အသံထုတ်ယူ၍မရပါ")
    return out_path


def make_thumbnail(video_path: str, out_jpg: str, at_sec: float = 1.0) -> str:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(at_sec), "-i", video_path,
         "-frames:v", "1", "-q:v", "4", out_jpg],
        capture_output=True)
    return out_jpg if os.path.exists(out_jpg) else ""


def wav_duration_ms(wav_path: str) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", wav_path], capture_output=True, text=True)
    try:
        return int(float(r.stdout.strip()) * 1000)
    except Exception:
        return 0


def has_audio_stream(path: str) -> bool:
    """True if the file contains at least one decodable audio stream."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index", "-of", "csv=p=0", path],
        capture_output=True, text=True)
    return bool(r.stdout.strip())


def normalize_narration(src: str, out_wav: str, target_ms: int = 0) -> str:
    """Convert a user-uploaded narration file (mp3/wav/m4a/ogg) to the
    pipeline's voice-track format: 44.1kHz mono wav. When target_ms is given,
    pad with silence (or trim) to exactly that length so the final video keeps
    its full duration instead of being cut by -shortest."""
    af = ["aresample=44100", "aformat=channel_layouts=mono"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-af", ",".join(af)]
    if target_ms > 0:
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-af",
               ",".join(af + ["apad"]), "-t", str(target_ms / 1000)]
    cmd += ["-c:a", "pcm_s16le", out_wav]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out_wav):
        raise RuntimeError("Narration ဖိုင်ဖတ်၍မရပါ: " + (r.stderr or "")[:300])
    return out_wav


def build_voice_track(segments: list[dict], out_wav: str,
                      total_ms: int) -> str:
    """Place each segment's wav at its start time -> single voice track."""
    inputs, filters, idx = [], [], 0
    # base silence
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
         "-i", f"anullsrc=r=44100:cl=mono:d={max(1, total_ms/1000)}",
         "-t", str(total_ms / 1000), "-c:a", "pcm_s16le", out_wav],
        capture_output=True)
    cur = out_wav
    for seg in segments:
        wav = seg.get("voice_wav")
        if not wav or not os.path.exists(wav):
            continue
        nxt = out_wav + f".mix{idx}.wav"
        delay = int(seg["start_ms"])
        f = (f"[1:a]adelay={delay}|{delay},apad[va];"
             f"[0:a][va]amix=inputs=2:duration=first:dropout_transition=0[aout]")
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", cur, "-i", wav,
             "-filter_complex", f, "-map", "[aout]",
             "-c:a", "pcm_s16le", nxt],
            capture_output=True, text=True)
        if r.returncode == 0:
            if cur != out_wav:
                os.unlink(cur)
            cur = nxt
            idx += 1
    if cur != out_wav:
        os.replace(cur, out_wav)
    return out_wav
