"""Caption grouping. Groups are contiguous slices of the timed word list; timestamps are never modified."""
from __future__ import annotations

import math
from dataclasses import dataclass

from .config import GroupingOptions
from .models import CaptionGroup, Word

_STRONG = ".!?\u2026"
_WEAK = ",;:\u2014\u2013-"
_CLOSERS = "\"'\u201d\u2019)]}\u00bb"
_ABBREV = {"mr.", "mrs.", "ms.", "dr.", "st.", "vs.", "prof.", "sr.", "jr."}
_FUNCTION_WORDS = {"a", "an", "the", "of", "to", "in", "on", "at", "for", "and", "but", "or", "with", "by", "from", "as", "my", "your", "his", "her", "our", "their", "that", "this"}


@dataclass(frozen=True)
class GroupingParams:
    mode: str
    max_words: int
    max_chars: int
    max_lines: int
    max_duration: float | None
    max_gap: float
    break_on_punctuation: bool
    split_long_sentences: bool


_MODE_DEFAULTS = {
    "phrase": dict(max_words=7, max_chars=44, max_lines=3, max_duration=4.5, max_gap=0.6, break_on_punctuation=True, split_long_sentences=True),
    "sentence": dict(max_words=16, max_chars=96, max_lines=4, max_duration=9.0, max_gap=0.9, break_on_punctuation=True, split_long_sentences=True),
    "short_form": dict(max_words=4, max_chars=26, max_lines=3, max_duration=2.8, max_gap=0.45, break_on_punctuation=True, split_long_sentences=True),
    "word": dict(max_words=1, max_chars=40, max_lines=1, max_duration=None, max_gap=10.0, break_on_punctuation=True, split_long_sentences=True),
}


def resolve_params(mode: str, opts: GroupingOptions | None = None) -> GroupingParams:
    d = dict(_MODE_DEFAULTS[mode])
    if opts is not None:
        for k, v in vars(opts).items():
            if v is not None:
                d[k] = v
    return GroupingParams(mode=mode, **d)


def _core(text: str) -> str:
    return text.rstrip(_CLOSERS)


def ends_strong(text: str) -> bool:
    t = _core(text)
    return bool(t) and t[-1] in _STRONG and t.lower() not in _ABBREV


def ends_weak(text: str) -> bool:
    t = _core(text)
    return bool(t) and t[-1] in _WEAK


def _chars(seg: list[Word]) -> int:
    return sum(len(w.text) for w in seg) + len(seg) - 1


def _fits(seg: list[Word], p: GroupingParams) -> bool:
    if len(seg) <= 1:
        return True
    if len(seg) > p.max_words or _chars(seg) > p.max_chars:
        return False
    return p.max_duration is None or (seg[-1].end - seg[0].start) <= p.max_duration


def _segments(words: list[Word], p: GroupingParams) -> list[list[Word]]:
    """Split at genuine gaps and (optionally) at sentence-ending punctuation."""
    segs: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur:
            gap = w.start - cur[-1].end
            if gap > p.max_gap or (p.break_on_punctuation and ends_strong(cur[-1].text)):
                segs.append(cur)
                cur = []
        cur.append(w)
    if cur:
        segs.append(cur)
    return segs


def _choose_cuts(seg: list[Word], p: GroupingParams, k: int, cum: list[int]) -> list[int]:
    n, total = len(seg), cum[-1]
    cuts: list[int] = []
    prev = 0
    for j in range(1, k):
        ideal = total * j / k
        best, best_score = None, math.inf
        for c in range(prev + 1, n - (k - j) + 1):
            score = abs(cum[c] - ideal) / (total / k) * 2.0
            last = seg[c - 1].text
            if ends_weak(last):
                score -= 1.5
            if last.lower().strip(".,;:!?\"'") in _FUNCTION_WORDS:
                score += 1.5
            if p.max_words > 1 and (c - prev < 2 or (j == k - 1 and n - c < 2)):
                score += 2.0
            score -= min(max(seg[c].start - seg[c - 1].end, 0.0), 0.5) * 4.0
            if score < best_score:
                best, best_score = c, score
        cuts.append(best)
        prev = best
    return cuts


def _split(seg: list[Word], p: GroupingParams) -> list[list[Word]]:
    n = len(seg)
    if _fits(seg, p) or not p.split_long_sentences:
        return [seg]
    if p.max_words == 1:
        return [[w] for w in seg]
    cum = [0]
    for w in seg:
        cum.append(cum[-1] + len(w.text) + 1)
    k = max(2, math.ceil(n / p.max_words), math.ceil(_chars(seg) / p.max_chars))
    if p.max_duration:
        k = max(k, math.ceil((seg[-1].end - seg[0].start) / p.max_duration))
    while k < n:
        cuts = [0] + _choose_cuts(seg, p, k, cum) + [n]
        chunks = [seg[a:b] for a, b in zip(cuts, cuts[1:])]
        if all(_fits(c, p) for c in chunks):
            return chunks
        k += 1
    return [[w] for w in seg]


def group_words(words: list[Word], p: GroupingParams) -> list[CaptionGroup]:
    groups: list[CaptionGroup] = []
    for seg in _segments(words, p):
        for chunk in _split(seg, p):
            groups.append(CaptionGroup(words=tuple(chunk)))
    return groups


def split_group(group: CaptionGroup) -> tuple[CaptionGroup, CaptionGroup] | None:
    """Split a group in two (used by layout when a group cannot fit). None for single words."""
    ws = list(group.words)
    if len(ws) < 2:
        return None
    cum = [0]
    for w in ws:
        cum.append(cum[-1] + len(w.text) + 1)
    p = resolve_params("phrase")
    (c,) = _choose_cuts(ws, p, 2, cum)
    return CaptionGroup(tuple(ws[:c])), CaptionGroup(tuple(ws[c:]))
