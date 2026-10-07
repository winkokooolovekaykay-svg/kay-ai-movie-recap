"""Video ingestion: upload validation, YouTube via yt-dlp, RedNote graceful fallback."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import uuid

ALLOWED_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
MIME_OK = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm",
           "video/x-msvideo", "video/avi", "application/octet-stream"}

YOUTUBE_RE = re.compile(
    r"^(https?://)?(www\.|m\.)?(youtube\.com/(watch|shorts|embed)|youtu\.be)/", re.I)
REDNOTE_RE = re.compile(r"(xiaohongshu\.com|rednote)", re.I)


def validate_extension(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(
            "ဖိုင်အမျိုးအစားမမှန်ပါ။ MP4/MOV/MKV/WEBM/AVI သာရပါတယ်။")
    return ext


def save_upload_stream(fileobj, dest_path: str, max_bytes: int,
                       progress_cb=None) -> int:
    written = 0
    chunk = 1024 * 256
    with open(dest_path, "wb") as f:
        while True:
            data = fileobj.read(chunk)
            if not data:
                break
            written += len(data)
            if written > max_bytes:
                f.close()
                os.unlink(dest_path)
                raise ValueError(
                    f"ဖိုင်ကြီးလွန်းပါတယ်။ {max_bytes//(1024*1024)}MB အောက်သုံးပါ။")
            f.write(data)
            if progress_cb:
                progress_cb(written)
    return written


def _ytdlp() -> str:
    exe = shutil.which("yt-dlp")
    if not exe:
        raise RuntimeError(
            "yt-dlp မရှိသေးပါ။ pip install yt-dlp လုပ်ပြီးမှ YouTube/RedNote သုံးနိုင်ပါမယ်။")
    return exe


def youtube_metadata(url: str) -> dict:
    exe = _ytdlp()
    r = subprocess.run(
        [exe, "--no-playlist", "--skip-download", "--print",
         "%(title)s|%(duration)s|%(channel)s|%(thumbnail)s|%(id)s", url],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("YouTube link ဖတ်၍မရပါ။ link မှန်မမှန်စစ်ပါ။")
    parts = (r.stdout.strip().split("\n")[0]).split("|")
    while len(parts) < 5:
        parts.append("")
    title, dur, channel, thumb, vid = parts[:5]
    return {"title": title, "duration": dur, "channel": channel,
            "thumbnail": thumb, "id": vid}


def download_video(url: str, out_dir: str, max_mb: int) -> str:
    """Download best mp4 (<=720p default) via yt-dlp. Returns file path."""
    exe = _ytdlp()
    name = f"dl_{uuid.uuid4().hex}.mp4"
    out = os.path.join(out_dir, name)
    r = subprocess.run(
        [exe, "--no-playlist",
         "-f", "bv*[height<=720]+ba/b[height<=720]/b",
         "--merge-output-format", "mp4",
         "--max-filesize", f"{max_mb}M",
         "-o", out, url],
        capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.exists(out):
        err = (r.stderr or "")[-500:]
        raise RuntimeError(f"ဗီဒီယို download လုပ်၍မရပါ။ {err}")
    return out


def check_rednote(url: str) -> None:
    """Raises with the spec's graceful message when direct import is blocked."""
    if not REDNOTE_RE.search(url):
        raise ValueError("RedNote (xiaohongshu.com) link မဟုတ်ပါ။")
    # We attempt via yt-dlp in the pipeline; this helper only validates shape.
