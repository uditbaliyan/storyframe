"""Input validation: duration compatibility and optional transcript matching. Never alters timestamps."""
from __future__ import annotations

import difflib
import re
import unicodedata

from .exceptions import DurationMismatchError, TranscriptMismatchError
from .models import Word


def check_duration(words: list[Word], textgrid_xmax: float, offset: float, audio_duration: float, tolerance: float, strict: bool, warnings: list[str]) -> None:
    """Alignment must fit inside the audio. Raises DurationMismatchError when strict, else warns."""
    last_end = words[-1].end
    problems = []
    if last_end > audio_duration + tolerance:
        problems.append(
            f"last word ends at {last_end:.3f}s but the audio is only {audio_duration:.3f}s long "
            f"(tolerance {tolerance:.2f}s). Wrong audio file, or a time offset is needed (--time-offset)"
        )
    tg_end = textgrid_xmax + offset
    if abs(tg_end - audio_duration) > tolerance:
        problems.append(
            f"TextGrid duration {tg_end:.3f}s differs from audio duration {audio_duration:.3f}s by more than {tolerance:.2f}s. "
            f"They may come from different recordings or a trimmed segment (consider --time-offset)"
        )
    if not problems:
        return
    if strict and any("only" in p for p in problems):
        raise DurationMismatchError("; ".join(problems))
    if strict:
        raise DurationMismatchError("; ".join(problems))
    warnings.extend(problems)


_EDGE_APOS = re.compile(r"^'+|'+$")


def normalize_token(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).casefold().replace("\u2019", "'").replace("\u2018", "'")
    t = re.sub(r"[^a-z0-9']", "", t)
    return _EDGE_APOS.sub("", t)


def tokenize_transcript(text: str) -> list[str]:
    """Whitespace tokens; tokens without letters/digits (e.g. a dash) attach to the previous token."""
    out: list[str] = []
    pending = ""
    for tok in text.split():
        if not any(c.isalnum() for c in tok):
            if out:
                out[-1] += tok
            else:
                pending += tok
            continue
        out.append(pending + tok)
        pending = ""
    return out


def apply_transcript(words: list[Word], transcript: str) -> list[Word]:
    """Replace display text with transcript tokens when the normalized sequences match exactly.

    Timestamps are never moved. On any difference, raises TranscriptMismatchError with a diff.
    """
    tokens = tokenize_transcript(transcript)
    a = [normalize_token(w.text) for w in words]
    b = [normalize_token(t) for t in tokens]
    if a == b:
        return [Word(text=t, start=w.start, end=w.end, original_text=w.original_text or w.text) for w, t in zip(words, tokens)]
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    diffs: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        when = f"{words[min(i1, len(words) - 1)].start:.2f}s"
        aligned = " ".join(w.text for w in words[i1:i2]) or "(nothing)"
        said = " ".join(tokens[j1:j2]) or "(nothing)"
        kind = {"replace": "differs", "delete": "in TextGrid only", "insert": "in transcript only"}[tag]
        diffs.append(f"near {when} [{kind}]: TextGrid={aligned!r} transcript={said!r}")
    shown = diffs[:15]
    more = f" (+{len(diffs) - 15} more)" if len(diffs) > 15 else ""
    raise TranscriptMismatchError(
        f"transcript does not match the {len(words)} timed words ({len(tokens)} transcript tokens). "
        f"Text was NOT shifted onto other timestamps. Differences: " + "; ".join(shown) + more,
        mismatches=diffs,
    )
