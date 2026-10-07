"""ffprobe-based video analysis."""
from __future__ import annotations
import json
import subprocess


def analyze(video_path: str) -> dict:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format",
         "-of", "json", video_path],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("ဗီဒီယိုဖိုင်ဖတ်၍မရပါ")
    data = json.loads(r.stdout or "{}")
    vstream = next((s for s in data.get("streams", [])
                    if s.get("codec_type") == "video"), {})
    astream = next((s for s in data.get("streams", [])
                    if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})
    width = int(vstream.get("width") or 0)
    height = int(vstream.get("height") or 0)
    fps = 0.0
    fr = vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "0/1"
    try:
        n, d = fr.split("/")
        fps = float(n) / float(d) if float(d) else 0.0
    except Exception:
        pass
    duration = float(fmt.get("duration") or 0)
    audio_info = ""
    if astream:
        audio_info = (f"{astream.get('codec_name','')} "
                      f"{astream.get('channels',0)}ch "
                      f"{astream.get('sample_rate','')}Hz")
    return {
        "duration_ms": int(duration * 1000),
        "width": width, "height": height,
        "fps": round(fps, 2),
        "has_audio": astream is not None,
        "audio_info": audio_info.strip(),
        "size_bytes": int(fmt.get("size") or 0),
        "format": fmt.get("format_name", ""),
    }
