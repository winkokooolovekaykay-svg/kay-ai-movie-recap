"""Video ingestion: upload validation only.

NOTE: URL import (YouTube/RedNote via yt-dlp) was removed to comply with
hosting Acceptable Use Policies. Users upload video files directly.
"""
from __future__ import annotations
import os

ALLOWED_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
MIME_OK = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm",
           "video/x-msvideo", "video/avi", "application/octet-stream"}


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
