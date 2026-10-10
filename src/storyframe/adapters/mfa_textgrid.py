"""MFA TextGrid adapter. The only module that knows about Praat TextGrid structure.

Uses ``praatio`` for parsing (handles long/short formats and encodings). This adapter selects the
word tier, validates intervals and returns normalized :class:`~storyframe.models.Word` records.
Alignment from other tools could be supported by writing another adapter returning ``AlignmentData``.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ..exceptions import TextGridError, TimingError, WordTierError
from ..models import AlignmentData, Word

DEFAULT_SILENCE_LABELS = frozenset({"", "sil", "sp", "silence", "<eps>", "<sil>", "{sil}", "<p:>", "#"})
_PHONE_NAME = re.compile(r"phone|phoneme|phn", re.I)
_WORD_NAME = re.compile(r"(^|[\s\-_:/])words?$", re.I)
_OVERLAP_EPS = 1e-6


def _open(path: Path):
    from praatio import textgrid

    try:
        return textgrid.openTextgrid(str(path), includeEmptyIntervals=True)
    except Exception as exc:  # praatio raises several unrelated types on malformed input
        raise TextGridError(f"cannot parse TextGrid {path}: {type(exc).__name__}: {exc}") from exc


def list_interval_tiers(path: Path) -> list[str]:
    tg = _open(Path(path))
    return [n for n in tg.tierNames if tg.getTier(n).tierType == "IntervalTier"]


def select_word_tier(tier_names: list[str], interval_tiers: list[str], explicit: str | None) -> tuple[str, list[str]]:
    """Return (tier_name, warnings). Raises WordTierError with an actionable message when unsafe."""
    listing = ", ".join(repr(n) for n in tier_names) or "(none)"
    if explicit is not None:
        if explicit in interval_tiers:
            return explicit, []
        ci = [n for n in interval_tiers if n.lower() == explicit.lower()]
        if len(ci) == 1:
            return ci[0], []
        if explicit in tier_names:
            raise WordTierError(f"tier {explicit!r} is not an interval tier. Interval tiers: {interval_tiers}")
        raise WordTierError(f"word tier {explicit!r} not found. Tiers in file: {listing}")
    if not interval_tiers:
        raise WordTierError(f"TextGrid has no interval tiers. Tiers in file: {listing}")
    named = [n for n in interval_tiers if _WORD_NAME.search(n.strip())]
    if len(named) == 1:
        return named[0], []
    if len(named) > 1:
        raise WordTierError(
            f"ambiguous word tier: several tiers look like word tiers ({named}), e.g. multiple speakers. "
            f"Choose one with --word-tier / RenderConfig(word_tier=...)."
        )
    non_phone = [n for n in interval_tiers if not _PHONE_NAME.search(n)]
    if len(interval_tiers) == 1 and len(non_phone) == 1:
        return non_phone[0], [f"tier {non_phone[0]!r} is the only interval tier; assuming it holds words (pass --word-tier to confirm)"]
    raise WordTierError(
        f"cannot identify the word tier safely. Interval tiers: {interval_tiers}. "
        f"Expected a tier named 'words' (or '<speaker> - words'). Choose one with --word-tier."
    )


def read_textgrid(path: str | Path, word_tier: str | None = None, silence_labels: Iterable[str] | None = None) -> AlignmentData:
    """Parse ``path`` and return the timed word sequence (TextGrid times, unshifted)."""
    path = Path(path)
    tg = _open(path)
    interval_tiers = [n for n in tg.tierNames if tg.getTier(n).tierType == "IntervalTier"]
    name, warnings = select_word_tier(list(tg.tierNames), interval_tiers, word_tier)
    tier = tg.getTier(name)
    silence = {s.strip().lower() for s in (DEFAULT_SILENCE_LABELS if silence_labels is None else silence_labels)}
    xmin, xmax = float(tg.minTimestamp), float(tg.maxTimestamp)

    words: list[Word] = []
    prev_end = None
    prev_label = None
    for iv in tier.entries:
        start, end, label = float(iv.start), float(iv.end), (iv.label or "").strip()
        if end < start:
            raise TimingError(f"interval {label!r} ends before it starts ({start:.3f}s > {end:.3f}s) in tier {name!r}")
        if start < xmin - _OVERLAP_EPS or end > xmax + _OVERLAP_EPS:
            raise TimingError(f"interval {label!r} [{start:.3f}, {end:.3f}] lies outside the TextGrid bounds [{xmin:.3f}, {xmax:.3f}]")
        if prev_end is not None and start < prev_end - _OVERLAP_EPS:
            raise TimingError(f"intervals overlap or are out of order: {prev_label!r} ends at {prev_end:.3f}s but {label!r} starts at {start:.3f}s")
        prev_end, prev_label = end, label
        if label.lower() in silence:
            continue
        if end - start <= 0:
            warnings.append(f"dropped zero-length word {label!r} at {start:.3f}s (no duration to display)")
            continue
        words.append(Word(text=label, start=start, end=end, original_text=label))
    if not words:
        raise WordTierError(f"tier {name!r} contains no spoken words after removing silence labels {sorted(silence)}")
    if any(w.text == "<unk>" for w in words):
        warnings.append("tier contains '<unk>' labels (words unknown to the MFA dictionary); supply the original transcript to display real text")
    return AlignmentData(words=words, tier_name=name, tier_names=list(tg.tierNames), xmin=xmin, xmax=xmax, warnings=warnings)
