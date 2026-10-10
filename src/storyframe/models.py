"""Typed data models shared across modules. All times are seconds (float)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class Word:
    """One aligned word. ``text`` is what is displayed; ``original_text`` is the TextGrid label."""

    text: str
    start: float
    end: float
    original_text: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict, compare=False, hash=False)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class CaptionGroup:
    """Words shown together. ``start``/``end`` are the exact first-start / last-end of the words."""

    words: tuple[Word, ...]
    visible_end: float | None = None  # set by timeline.schedule_groups

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    audio_codec: str | None
    sample_rate: int | None
    channels: int | None


@dataclass
class AlignmentData:
    words: list[Word]
    tier_name: str
    tier_names: list[str]
    xmin: float
    xmax: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def format(self) -> str:
        lines = [f"{k}: {v}" for k, v in self.info.items()]
        lines += [f"WARNING: {w}" for w in self.warnings]
        lines += [f"ERROR: {e}" for e in self.errors]
        lines.append("RESULT: " + ("OK" if self.ok else "FAILED"))
        return "\n".join(lines)


@dataclass
class RenderResult:
    output_path: Path | None
    duration: float
    resolution: tuple[int, int]
    fps: float
    frames: int
    num_words: int
    num_groups: int
    warnings: list[str]
    render_seconds: float
    verification: dict[str, Any]
    dry_run: bool = False
