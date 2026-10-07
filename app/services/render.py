"""Final rendering with ffmpeg: voice mixing, subtitle burn-in, subtitle masking,
resolution/fps/aspect presets."""
from __future__ import annotations
import os
import subprocess

QUALITY_PRESETS = {
    "fast":      ["-preset", "ultrafast", "-crf", "26"],
    "balanced":  ["-preset", "medium", "-crf", "22"],
    "high":      ["-preset", "slow", "-crf", "19"],
    "maximum":   ["-preset", "veryslow", "-crf", "17"],
}
RES_H = {"1080p": 1080, "720p": 720, "480p": 480}
FPS_MAP = {"30": "30", "60": "60"}


def _scale_pad(aspect: str, res_h: int | None) -> str | None:
    """Returns vf for aspect conversion, or None to keep original."""
    if aspect == "original":
        if res_h:
            return f"scale=-2:{res_h}"
        return None
    h = res_h or 1080
    targets = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080)}
    if aspect not in targets:
        return None
    W, H = targets[aspect]
    # fit inside then pad
    return (f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2")


def render(video_path: str, *, ass_path: str = "", voice_wav: str = "",
           orig_audio_wav: str = "", orig_volume: int = 15,
           mute_original: bool = True,
           mask: dict | None = None,
           preset: str = "original", fps: str = "original",
           aspect: str = "original", quality: str = "balanced",
           out_path: str = "", progress_cb=None) -> str:
    inputs = ["-i", video_path]
    maps = ["-map", "0:v:0"]
    ac = ["-c:a", "aac", "-b:a", "160k"]
    vfs: list[str] = []

    # --- subtitle-region mask (blur or solid box) ---
    if mask and mask.get("enabled") and mask.get("w", 0) > 0 and mask.get("h", 0) > 0:
        x, y, w, h = mask["x"], mask["y"], mask["w"], mask["h"]
        if mask.get("type") == "solid":
            vfs.append(f"drawbox=x={x}:y={y}:w={w}:h={h}:color=black@0.85:t=fill")
        else:  # blur
            vfs.append(
                f"split[a][b];[a]crop={w}:{h}:{x}:{y},boxblur=12:2[bb];"
                f"[b][bb]overlay={x}:{y}")

    # --- aspect / resolution ---
    res_h = RES_H.get(preset)
    sp = _scale_pad(aspect, res_h)
    if sp:
        vfs.append(sp)

    # --- subtitle burn-in (after scaling so ASS PlayRes matches) ---
    if ass_path and os.path.exists(ass_path):
        esc = ass_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "")
        vfs.append(f"ass='{esc}'")

    # --- audio: voice track + original background ---
    audio_filters: list[str] = []
    a_inputs = 1  # 0 is video
    has_voice = bool(voice_wav and os.path.exists(voice_wav))
    use_orig = bool(orig_audio_wav and os.path.exists(orig_audio_wav)
                    and not mute_original)
    if has_voice:
        inputs += ["-i", voice_wav]
        v_idx = a_inputs
        a_inputs += 1
        audio_filters.append(f"[{v_idx}:a]volume=1.0[vv]")
    if use_orig:
        inputs += ["-i", orig_audio_wav]
        o_idx = a_inputs
        a_inputs += 1
        vol = max(0, min(100, orig_volume)) / 100.0
        audio_filters.append(f"[{o_idx}:a]volume={vol:.2f}[bg]")
    if has_voice and use_orig:
        audio_filters.append(
            "[vv][bg]amix=inputs=2:duration=longest:dropout_transition=0[mixout]")
        maps = ["-map", "0:v:0", "-map", "[mixout]"]
    elif has_voice:
        # voice track is a filter output; mapping the raw input pad would
        # conflict with the filter graph, so map the filtered label.
        maps = ["-map", "0:v:0", "-map", "[vv]"]
    elif use_orig:
        maps = ["-map", "0:v:0", "-map", "[bg]"]

    cmd = ["ffmpeg", "-y", "-v", "error", "-progress", "pipe:1"]
    cmd += inputs
    if vfs:
        cmd += ["-vf", ",".join(vfs)]
    if audio_filters:
        cmd += ["-filter_complex", ";".join(audio_filters)]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"] + QUALITY_PRESETS.get(
        quality, QUALITY_PRESETS["balanced"])
    if fps in FPS_MAP:
        cmd += ["-r", FPS_MAP[fps]]
    cmd += maps + ac + ["-movflags", "+faststart", "-shortest", out_path]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True)
    # parse progress (out_time_ms / duration)
    dur_ms = _video_duration_ms(video_path)
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if line.startswith("out_time_ms=") and progress_cb and dur_ms:
                try:
                    ms = int(line.split("=")[1])
                    progress_cb(min(99, int(ms / dur_ms * 100)))
                except Exception:
                    pass
            if line.startswith("progress=end"):
                break
    finally:
        proc.wait()
    if proc.returncode != 0:
        err = (proc.stderr.read() or "")[-600:] if proc.stderr else ""
        raise RuntimeError("ဗီဒီယို render လုပ်၍မရပါ။ " + err)
    return out_path


def _video_duration_ms(path: str) -> int:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return int(float(r.stdout.strip()) * 1000)
    except Exception:
        return 0
