"""Background job manager + 12-stage processing pipeline."""
from __future__ import annotations
import os
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from . import db
from .config import TMP_DIR, EXPORT_DIR, PROJECT_DIR, settings
from .providers import ProviderUnavailable
from .providers import stt as stt_provider
from .providers import tts as tts_provider
from .services import audio as audio_svc
from .services import subtitle as sub_svc
from .services import render as render_svc

executor = ThreadPoolExecutor(max_workers=2)

STAGES = [
    "uploading", "analyzing", "extracting_audio", "transcribing",
    "translating", "creating_recap", "generating_voice", "synchronizing",
    "detecting_subtitles", "subtitle_overlay", "rendering", "finalizing",
]
STAGE_MM = {
    "uploading": "တင်နေသည်", "analyzing": "ဗီဒီယိုစစ်ဆေးနေသည်",
    "extracting_audio": "အသံထုတ်ယူနေသည်", "transcribing": "အသံစာသားထုတ်နေသည်",
    "translating": "မြန်မာဘာသာပြန်နေသည်", "creating_recap": "Recap ရေးနေသည်",
    "generating_voice": "မြန်မာအသံထုတ်နေသည်", "synchronizing": "အသံညှိနေသည်",
    "detecting_subtitles": "စာတန်းနေရာရှာနေသည်",
    "subtitle_overlay": "မြန်မာစာတန်းထည့်နေသည်", "rendering": "ဗီဒီယို render လုပ်နေသည်",
    "finalizing": "အပြီးသတ်နေသည်",
}

MODE_FLAGS = {
    # stt, translate/recap, subs, voice, render
    "translate":      dict(stt=True,  text="translate", subs=False, voice=False, render=False),
    "subtitle":       dict(stt=True,  text="translate", subs=True,  voice=False, render=True),
    "voice":          dict(stt=True,  text="translate", subs=False, voice=True,  render=True),
    "voice_subtitle": dict(stt=True,  text="translate", subs=True,  voice=True,  render=True),
    "recap":          dict(stt=True,  text="recap",     subs=True,  voice=True,  render=True),
    "short":          dict(stt=True,  text="short",     subs=True,  voice=True,  render=True),
}


def _update(job_id: int, **kw):
    conn = db.get_db()
    try:
        sets = ", ".join(f"{k}=?" for k in kw) + ", updated_at=?"
        vals = list(kw.values()) + [db.now_ms()]
        conn.execute(f"UPDATE jobs SET {sets} WHERE id=?", vals + [job_id])
        conn.commit()
    finally:
        conn.close()


def _set_stage(job_id: int, stage: str, progress: int = 0):
    idx = STAGES.index(stage) if stage in STAGES else 0
    _update(job_id, stage=stage, stage_index=idx, progress=progress,
            status="running")


def _get_job(job_id: int) -> dict:
    conn = db.get_db()
    try:
        return db.row_to_dict(
            conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
    finally:
        conn.close()


def _get_project(pid: int) -> dict:
    conn = db.get_db()
    try:
        return db.row_to_dict(
            conn.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone())
    finally:
        conn.close()


def _get_segments(pid: int) -> list[dict]:
    conn = db.get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM segments WHERE project_id=? ORDER BY idx", (pid,)).fetchall()
        return [db.row_to_dict(r) for r in rows]
    finally:
        conn.close()


def _save_segments(pid: int, segments: list[dict]):
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM segments WHERE project_id=?", (pid,))
        for i, s in enumerate(segments):
            conn.execute(
                "INSERT INTO segments(project_id, idx, start_ms, end_ms, "
                "original_text, burmese_text, voice_text, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (pid, i, int(s["start_ms"]), int(s["end_ms"]),
                 s.get("original_text", ""), s.get("burmese_text", ""),
                 s.get("voice_text", ""), db.now_ms()))
        conn.execute("UPDATE projects SET updated_at=? WHERE id=?",
                     (db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()


def _charge(user_id: int, project: dict, mode: str):
    minutes = max(1, (project.get("duration_ms") or 60000) / 60000)
    flags = MODE_FLAGS.get(mode, MODE_FLAGS["voice_subtitle"])
    if mode in ("recap", "short"):
        rate = float(db.get_setting("credit_price_recap_per_min", "15"))
    elif flags["voice"]:
        rate = float(db.get_setting("credit_price_voice_per_min", "5"))
    else:
        rate = float(db.get_setting("credit_price_video_per_min", "10"))
    cost = round(minutes * rate, 2)
    conn = db.get_db()
    try:
        row = conn.execute("SELECT credits FROM users WHERE id=?",
                           (user_id,)).fetchone()
        credits = row["credits"] if row else 0
        if credits < cost:
            raise ProviderUnavailable(
                f"Credit မလုံလောက်ပါ။ လိုအပ်ချက် {cost}, လက်ကျန် {credits}။")
        conn.execute("UPDATE users SET credits=credits-? WHERE id=?",
                     (cost, user_id))
        conn.commit()
    finally:
        conn.close()
    return cost


def create_job(project_id: int, user_id: int, kind: str = "pipeline") -> int:
    conn = db.get_db()
    try:
        cur = conn.execute(
            "INSERT INTO jobs(project_id, user_id, kind, stage, status, "
            "created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (project_id, user_id, kind, "queued", "queued",
             db.now_ms(), db.now_ms()))
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def launch(job_id: int):
    executor.submit(_run, job_id)


def _run(job_id: int):
    job = _get_job(job_id)
    pid, uid = job["project_id"], job["user_id"]
    try:
        project = _get_project(pid)
        mode = project.get("mode") or "voice_subtitle"
        flags = MODE_FLAGS.get(mode, MODE_FLAGS["voice_subtitle"])
        _charge(uid, project, mode)
        _pipeline(job_id, project, flags)
        _update(job_id, status="done", progress=100, stage="finalizing",
                stage_index=len(STAGES) - 1)
    except ProviderUnavailable as e:
        _update(job_id, status="failed", error=str(e))
    except Exception as e:  # never crash silently
        traceback.print_exc()
        _update(job_id, status="failed",
                error=f"လုပ်ဆောင်ရာတွင် အမှားဖြစ်နေပါတယ်: {e}")


def _pipeline(job_id: int, project: dict, flags: dict):
    from .services import text_ai
    pid = project["id"]
    workdir = PROJECT_DIR / str(pid)
    workdir.mkdir(parents=True, exist_ok=True)
    video = project["video_path"]
    if not video or not os.path.exists(video):
        raise ProviderUnavailable("ဗီဒီယိုဖိုင်မတွေ့ပါ။ ပြန်တင်ပါ။")

    _set_stage(job_id, "uploading", 100)

    # ---- analyzing ----
    _set_stage(job_id, "analyzing", 10)
    from .services import analyze as analyze_svc
    info = analyze_svc.analyze(video)
    conn = db.get_db()
    try:
        conn.execute(
            "UPDATE projects SET duration_ms=?, width=?, height=?, fps=?, "
            "has_audio=?, updated_at=? WHERE id=?",
            (info["duration_ms"], info["width"], info["height"], info["fps"],
             int(info["has_audio"]), db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()
    project.update(info)
    _set_stage(job_id, "analyzing", 100)

    # ---- extracting audio ----
    _set_stage(job_id, "extracting_audio", 20)
    wav16 = str(workdir / "audio16k.wav")
    audio_full = str(workdir / "audio_full.wav")
    has_audio = bool(info["has_audio"])
    if has_audio:
        audio_svc.extract_wav(video, wav16)
        audio_svc.extract_audio_track(video, audio_full)
    _set_stage(job_id, "extracting_audio", 100)

    segments = _get_segments(pid)

    # ---- transcribing ----
    _set_stage(job_id, "transcribing", 5)
    if flags["stt"] and has_audio:
        if not segments or not any(s.get("original_text") for s in segments):
            def cb(p=None):
                pass
            raw = stt_provider.transcribe(wav16, progress_cb=cb)
            segments = [{"start_ms": s["start_ms"], "end_ms": s["end_ms"],
                         "original_text": s["text"], "burmese_text": "",
                         "voice_text": ""} for s in raw]
            detected = ""
            if raw:
                detected = text_ai.detect_language(
                    " ".join(s["text"] for s in raw[:20]))
                c2 = db.get_db()
                try:
                    c2.execute("UPDATE projects SET detected_language=? WHERE id=?",
                               (detected, pid))
                    c2.commit()
                finally:
                    c2.close()
            _save_segments(pid, segments)
            segments = _get_segments(pid)  # re-fetch: fresh dicts lack DB ids
    elif flags["stt"] and not has_audio:
        raise ProviderUnavailable("ဗီဒီယိုမှာ အသံလမ်းကြောင်းမရှိပါ။")
    _set_stage(job_id, "transcribing", 100)

    # ---- translating / recap ----
    text_kind = flags["text"]
    _set_stage(job_id, "translating" if text_kind == "translate" else "creating_recap", 5)
    if text_kind and segments:
        need = [s for s in segments if not s.get("burmese_text")]
        if need:
            if text_kind == "translate":
                out = text_ai.translate_segments(need, project.get("language") or "auto")
            elif text_kind == "short":
                out = text_ai.recap_segments(need, short=True)
            else:
                out = text_ai.recap_segments(need)
            by_id = {s["id"]: t for s, t in zip(need, out)}
            for s in segments:
                if s["id"] in by_id:
                    s["burmese_text"] = by_id[s["id"]]
                    s["voice_text"] = by_id[s["id"]]
            _save_segments(pid, segments)
    _set_stage(job_id, "translating", 100)
    _set_stage(job_id, "creating_recap", 100)

    # ---- generating voice ----
    _set_stage(job_id, "generating_voice", 5)
    voice_wav = ""
    if flags["voice"]:
        custom = (project.get("narration_mp3") or "").strip()
        if custom and os.path.exists(custom):
            # User-uploaded narration (e.g. made in Lovevoice): use it as the
            # voiceover track directly, no Google TTS needed. Pad/trim to the
            # video length so the export keeps its full duration.
            voice_wav = str(workdir / "voice_custom.wav")
            audio_svc.normalize_narration(
                custom, voice_wav,
                target_ms=info.get("duration_ms") or project.get("duration_ms") or 0)
            _set_stage(job_id, "generating_voice", 100)
        else:
            if not tts_provider.is_configured():
                raise ProviderUnavailable(tts_provider.requirement_message())
            voice_id = project.get("voice_id") or settings.TTS_DEFAULT_VOICE
            if not voice_id:
                voices = tts_provider.list_voices()
                if not voices:
                    raise ProviderUnavailable("မြန်မာအသံ မတွေ့ပါ။")
                voice_id = voices[0]["id"]
            vdir = workdir / "voice"
            vdir.mkdir(exist_ok=True)
            total = len(segments)
            for i, s in enumerate(segments):
                txt = (s.get("voice_text") or s.get("burmese_text") or "").strip()
                if not txt:
                    continue
                out = str(vdir / f"seg{i:04d}.wav")
                tts_provider.synthesize(txt, voice_id,
                                        speed=float(project.get("voice_speed") or 1.0),
                                        pitch=project.get("voice_pitch") or "normal",
                                        out_path=out)
                s["voice_wav"] = out
                _set_stage(job_id, "generating_voice", int((i + 1) / max(1, total) * 90))
            voice_track = str(workdir / "voice_track.wav")
            audio_svc.build_voice_track(segments, voice_track,
                                        project.get("duration_ms") or info["duration_ms"])
            voice_wav = voice_track
            _set_stage(job_id, "generating_voice", 100)
    else:
        _set_stage(job_id, "generating_voice", 100)

    # ---- synchronizing ----
    _set_stage(job_id, "synchronizing", 50)
    segments = sub_svc.fix_timing(segments)
    _save_segments(pid, segments)
    _set_stage(job_id, "synchronizing", 100)

    # ---- detecting subtitles ----
    _set_stage(job_id, "detecting_subtitles", 30)
    mask = None
    if project.get("mask_enabled") and project.get("mask_w"):
        mask = {"enabled": True, "x": project["mask_x"], "y": project["mask_y"],
                "w": project["mask_w"], "h": project["mask_h"],
                "type": project.get("mask_type") or "blur"}
    else:
        # heuristic default: bottom 14% band suggestion saved for UI
        w, h = info["width"], info["height"]
        if w and h:
            conn = db.get_db()
            try:
                conn.execute(
                    "UPDATE projects SET mask_x=?, mask_y=?, mask_w=?, mask_h=? "
                    "WHERE id=? AND mask_w=0",
                    (int(w * 0.1), int(h * 0.84), int(w * 0.8), int(h * 0.14), pid))
                conn.commit()
            finally:
                conn.close()
    _set_stage(job_id, "detecting_subtitles", 100)

    # ---- subtitle overlay ----
    _set_stage(job_id, "subtitle_overlay", 20)
    ass_path = ""
    if flags["subs"]:
        ass_path = str(workdir / "burmese.ass")
        sub_svc.build_ass(segments, style=project.get("subtitle_style") or "clean",
                          position=project.get("subtitle_position") or "bottom",
                          out_path=ass_path)
    _set_stage(job_id, "subtitle_overlay", 100)

    if not flags["render"]:
        # translate-only mode: produce SRT + script downloads
        srt = str(workdir / "burmese.srt")
        txt = str(workdir / "recap_script.txt")
        sub_svc.build_srt(segments, srt)
        sub_svc.build_script_txt(segments, project.get("name") or "recap", txt)
        _record_export(pid, "srt", srt)
        _record_export(pid, "script", txt)
        _set_stage(job_id, "rendering", 100)
        _set_stage(job_id, "finalizing", 100)
        return

    # ---- rendering ----
    _set_stage(job_id, "rendering", 5)

    def prog(p):
        _set_stage(job_id, "rendering", 5 + int(p * 0.9))

    out_mp4 = str(EXPORT_DIR / f"project_{pid}_job_{job_id}.mp4")
    render_svc.render(
        video, ass_path=ass_path, voice_wav=voice_wav,
        orig_audio_wav=audio_full if has_audio else "",
        orig_volume=int(project.get("orig_audio_volume") or 15),
        mute_original=not bool(project.get("orig_audio_enabled")),
        mask=mask,
        preset=project.get("export_preset") or "original",
        fps=project.get("export_fps") or "original",
        aspect=project.get("export_aspect") or "original",
        quality=project.get("export_quality") or "balanced",
        out_path=out_mp4, progress_cb=prog)
    _record_export(pid, "video", out_mp4)

    # also export srt + script + audio-only
    srt = str(workdir / "burmese.srt")
    txt = str(workdir / "recap_script.txt")
    sub_svc.build_srt(segments, srt)
    sub_svc.build_script_txt(segments, project.get("name") or "recap", txt)
    _record_export(pid, "srt", srt)
    _record_export(pid, "script", txt)
    if voice_wav and os.path.exists(voice_wav):
        _record_export(pid, "audio", voice_wav)

    _set_stage(job_id, "rendering", 100)

    # ---- finalizing: quality check ----
    _set_stage(job_id, "finalizing", 40)
    _quality_check(out_mp4, segments, flags)
    _cleanup_tmp(workdir)
    conn = db.get_db()
    try:
        conn.execute("UPDATE projects SET status='done', updated_at=? WHERE id=?",
                     (db.now_ms(), pid))
        conn.commit()
    finally:
        conn.close()
    _update(job_id, result_path=out_mp4)
    _set_stage(job_id, "finalizing", 100)


def _record_export(pid: int, kind: str, path: str):
    conn = db.get_db()
    try:
        conn.execute("DELETE FROM exports WHERE project_id=? AND kind=?", (pid, kind))
        conn.execute(
            "INSERT INTO exports(project_id, kind, file_path, created_at) "
            "VALUES (?,?,?,?)", (pid, kind, path, db.now_ms()))
        conn.commit()
    finally:
        conn.close()


def _quality_check(mp4: str, segments: list[dict], flags: dict):
    problems = []
    if not os.path.exists(mp4) or os.path.getsize(mp4) < 1024:
        problems.append("output file missing")
    if flags.get("subs"):
        subs = [s for s in segments if s.get("burmese_text", "").strip()]
        if not subs:
            problems.append("no burmese subtitle text")
        # overlaps
        ordered = sorted(segments, key=lambda s: s["start_ms"])
        for a, b in zip(ordered, ordered[1:]):
            if b["start_ms"] < a["end_ms"]:
                problems.append("subtitle overlap")
                break
    if problems:
        raise ProviderUnavailable(
            "Export မလုပ်ခင် ပြဿနာတစ်ခုတွေ့ရှိပါတယ်: " + ", ".join(problems))


def _cleanup_tmp(workdir):
    # keep workdir (voice wavs, ass) for resume; only drop stt chunks in TMP_DIR
    import shutil
    for name in os.listdir(TMP_DIR):
        if name.startswith("stt_"):
            shutil.rmtree(os.path.join(TMP_DIR, name), ignore_errors=True)
