"""Gemini-powered text AI: language detection, natural Burmese translation,
and movie-recap narration in professional Burmese storyteller style."""
from __future__ import annotations
from ..providers import ai as gemini

STORYTELLER_STYLE = """You are a professional Burmese movie-recap narrator (like popular Myanmar
YouTube recap channels). Write NATURAL Myanmar Burmese — never literal
machine translation. Rules:
- Natural Burmese grammar and sentence flow, correct Myanmar spelling (Unicode).
- Conversational storyteller tone, engaging and dramatic where fitting.
- Preserve characters, events, relationships, emotions, humor, and the ending.
- Never invent characters, events, or scenes not in the source.
- If something is unclear, preserve the uncertainty — do not hallucinate.
- Avoid unnecessary English words; translate names sensibly.
Example tone: "ဒီဇာတ်လမ်းကတော့ အစကတည်းက ထူးဆန်းတဲ့အဖြစ်အပျက်တစ်ခုနဲ့ စတင်လာပါတယ်။"
"""


def detect_language(sample_text: str) -> str:
    if not sample_text.strip():
        return ""
    try:
        out = gemini.generate_text(
            "Detect the language of this text. Reply with ONLY the English "
            f"language name (e.g. Chinese, English, Korean, Japanese, Thai):\n{sample_text[:2000]}")
        return out.strip().split("\n")[0][:30]
    except Exception:
        return ""


def translate_segments(segments: list[dict], src_lang: str = "auto") -> list[str]:
    """Faithful but natural Burmese translation, one output line per segment.

    Uses a neutral translation prompt (not the storyteller persona): the
    dramatic framing can trip safety filters on romance/drama content, while
    plain translation of the same text passes fine.
    """
    numbered = "\n".join(
        f"[{i}] {s.get('original_text','')}" for i, s in enumerate(segments))
    prompt = ("Translate the following narration lines into natural Myanmar "
              "Burmese (Unicode). Use natural Burmese grammar and sentence flow, "
              "correct Myanmar spelling. Keep the SAME numbering, one Burmese "
              "line per number, format exactly like: [0] <burmese>\n\n"
              + numbered)
    out = gemini.generate_text(prompt, timeout=180)
    results = [""] * len(segments)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("["):
            try:
                num, txt = line[1:].split("]", 1)
                results[int(num.strip())] = txt.strip()
            except Exception:
                continue
    return results


def recap_segments(segments: list[dict], short: bool = False) -> list[str]:
    """Rewrite dialogue into engaging Burmese recap narration, timed per segment."""
    numbered = "\n".join(
        f"[{i}] ({s['start_ms']/1000:.1f}s) {s.get('original_text','')}"
        for i, s in enumerate(segments))
    length = ("Keep it SHORT — a punchy narration for TikTok/Shorts/Reels, "
              "30-60% of the detail, never drop critical plot points."
              if short else
              "Write a full engaging recap narration covering all important "
              "plot points, in the same number of segments.")
    prompt = (STORYTELLER_STYLE +
              "\nRewrite the following timestamped dialogue into Burmese movie-recap "
              "narration. " + length + " Keep the SAME numbering and count, "
              "one narration line per number, format exactly like: [0] <burmese narration>. "
              "Each line must fit its timestamp (short spoken line, ~2 lines of subtitle).\n\n"
              + numbered)
    out = gemini.generate_text(prompt, timeout=240)
    results = [""] * len(segments)
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("["):
            try:
                num, txt = line[1:].split("]", 1)
                results[int(num.strip())] = txt.strip()
            except Exception:
                continue
    # fall back: keep any untranslated lines as-is rather than empty
    for i, s in enumerate(segments):
        if not results[i]:
            results[i] = s.get("original_text", "")
    return results
