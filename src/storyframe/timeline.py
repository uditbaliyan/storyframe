"""Word timeline utilities: offsetting, caption visibility scheduling, active-word lookup.

Nothing here invents or redistributes timestamps: every output time is an input word time or a
fixed offset from one (linger/fade windows).
"""
from __future__ import annotations

import dataclasses
from bisect import bisect_right

from .exceptions import TimingError
from .models import CaptionGroup, Word


def apply_offset(words: list[Word], offset: float) -> list[Word]:
    """Shift every word by ``offset`` seconds (user-supplied). Negative resulting starts are an error."""
    if offset == 0:
        return list(words)
    shifted = [dataclasses.replace(w, start=w.start + offset, end=w.end + offset) for w in words]
    first_bad = next((w for w in shifted if w.start < 0), None)
    if first_bad is not None:
        raise TimingError(f"time offset {offset:+.3f}s moves word {first_bad.text!r} before 0s ({first_bad.start:.3f}s); the offset is wrong for this audio")
    return shifted


def schedule_groups(groups: list[CaptionGroup], linger: float, exit_duration: float, fade_exit: bool = True) -> list[CaptionGroup]:
    """Set ``visible_end`` on each group.

    A group stays up for ``linger`` (+ fade-out) after its last word, but never past the next group's
    start, so stale text never remains across a genuine gap.
    """
    tail = linger + (exit_duration if fade_exit else 0.0)
    out = []
    for i, g in enumerate(groups):
        limit = groups[i + 1].start if i + 1 < len(groups) else float("inf")
        out.append(dataclasses.replace(g, visible_end=min(g.end + tail, limit)))
    return out


def active_word_index(group: CaptionGroup, t: float) -> int:
    """Index of the word whose MFA interval contains ``t`` (start <= t < end), else -1."""
    for i, w in enumerate(group.words):
        if w.start <= t < w.end:
            return i
    return -1


def revealed_count(group: CaptionGroup, t: float) -> int:
    """Number of words that have started by time ``t``."""
    return bisect_right([w.start for w in group.words], t)
