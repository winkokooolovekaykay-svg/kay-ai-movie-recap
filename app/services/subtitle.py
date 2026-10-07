"""Burmese subtitle engineering: ASS generation, 5 styles, auto line-break."""
from __future__ import annotations

FONT = "Noto Sans Myanmar"

# style_name -> (Fontsize, PrimaryColour, OutlineColour, BackColour, BorderStyle,
#               Outline, Shadow, Bold, Alignment, MarginV)
STYLES = {
    "clean":   dict(size=54, color="&H00FFFFFF", outline_c="&H99000000",
                    back="&H00000000", border=1, ol=2, sh=1, bold=0, align=2, mv=45),
    "cinema":  dict(size=52, color="&H00FFFFFF", outline_c="&HCC000000",
                    back="&H00000000", border=1, ol=1, sh=2, bold=0, align=2, mv=50),
    "youtube": dict(size=60, color="&H00FFFFFF", outline_c="&HFF000000",
                    back="&H99000000", border=3, ol=2, sh=0, bold=-1, align=2, mv=40),
    "tiktok":  dict(size=64, color="&H00FFFFFF", outline_c="&HFF101010",
                    back="&H00000000", border=1, ol=3, sh=2, bold=-1, align=2, mv=220),
    "minimal": dict(size=44, color="&H00FFFFFF", outline_c="&HAA000000",
                    back="&H00000000", border=1, ol=1, sh=1, bold=0, align=2, mv=40),
}

POSITION_ALIGN = {"bottom": 2, "middle": 8, "top": 6}
# (x, y) offsets for custom positioning handled via margins in ASS; we map:
POSITION_MARGIN = {
    "bottom": 45, "middle": 0, "top": 45,
    # tiktok safe-area handled by bigger bottom margin in style
}


def auto_line_break(text: str, max_chars: int = 40) -> str:
    """Break Burmese text into readable lines (Burmese uses spaces between
    phrases, so break on spaces; hard-break long runs).

    Note: max_chars counts Unicode code points. Burmese script uses many
    combining marks per visual character, so ~40 code points ≈ one comfortable
    subtitle line; 20 would stack 6-8 thin lines up the screen.
    """
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            # hard-break an overlong single word
            while len(w) > max_chars:
                lines.append(w[:max_chars])
                w = w[max_chars:]
            cur = w
    if cur:
        lines.append(cur)
    return "\\N".join(lines)


def _ms_to_ass(ms: int) -> str:
    total_s, milli = divmod(int(ms), 1000)
    m, s = divmod(total_s, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}.{milli // 10:02d}"


def build_ass(segments: list[dict], style: str = "clean",
              position: str = "bottom", out_path: str = "") -> str:
    st = STYLES.get(style, STYLES["clean"]).copy()
    if position in POSITION_ALIGN:
        st["align"] = POSITION_ALIGN[position]
        if position == "middle":
            st["mv"] = 0
        elif position == "top":
            st["mv"] = 45
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Burmese,{FONT},{st['size']},{st['color']},&H000019FF,{st['outline_c']},{st['back']},{st['bold']},0,0,0,100,100,0,0,{st['border']},{st['ol']},{st['sh']},{st['align']},30,30,{st['mv']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for seg in segments:
        txt = seg.get("burmese_text", "").strip()
        if not txt:
            continue
        start, end = int(seg["start_ms"]), int(seg["end_ms"])
        if end <= start:
            continue
        broken = auto_line_break(txt)
        # escape ASS special chars
        broken = broken.replace("{", "\\{").replace("}", "\\}")
        events.append(
            f"Dialogue: 0,{_ms_to_ass(start)},{_ms_to_ass(end)},Burmese,,0,0,0,,{broken}")
    ass = header + "\n".join(events) + "\n"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(ass)
    return out_path


def build_srt(segments: list[dict], out_path: str) -> str:
    def ts(ms: int) -> str:
        h, rem = divmod(ms, 3600000)
        m, rem = divmod(rem, 60000)
        s, mmm = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{mmm:03d}"
    lines = []
    n = 1
    for seg in segments:
        txt = seg.get("burmese_text", "").strip()
        if not txt:
            continue
        start, end = int(seg["start_ms"]), int(seg["end_ms"])
        if end <= start:
            continue
        lines.append(f"{n}\n{ts(start)} --> {ts(end)}\n"
                     f"{auto_line_break(txt).replace(chr(92)+'N', chr(10))}\n")
        n += 1
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def build_script_txt(segments: list[dict], title: str, out_path: str) -> str:
    lines = [title, "=" * len(title), ""]
    for seg in segments:
        lines.append(
            f"[{seg['idx']:03d}] {seg['start_ms']/1000:.1f}s -> {seg['end_ms']/1000:.1f}s")
        if seg.get("original_text"):
            lines.append(f"မူရင်း: {seg['original_text']}")
        lines.append(f"မြန်မာ: {seg.get('burmese_text','')}")
        lines.append("")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path


def fix_timing(segments: list[dict], min_dur: int = 800,
               max_dur: int = 8000) -> list[dict]:
    """Smart timing: no overlaps, clamp durations, keep order. Returns fixed list."""
    segs = sorted(segments, key=lambda s: (s["start_ms"], s["end_ms"]))
    prev_end = 0
    for s in segs:
        if s["start_ms"] < prev_end:
            s["start_ms"] = prev_end
        dur = s["end_ms"] - s["start_ms"]
        if dur < min_dur:
            s["end_ms"] = s["start_ms"] + min_dur
        elif dur > max_dur:
            s["end_ms"] = s["start_ms"] + max_dur
        prev_end = s["end_ms"]
    return segs
