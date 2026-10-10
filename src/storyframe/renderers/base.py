"""Renderer interface. A renderer consumes a fully-resolved RenderPlan; it never sees TextGrids."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from ..config import RenderConfig
from ..layout import CaptionLayout, ScrollLayout
from ..models import CaptionGroup, MediaInfo
from ..themes import Theme

ProgressFn = Callable[[str, float], None]


@dataclass
class RenderPlan:
    audio: MediaInfo
    groups: list[CaptionGroup]
    layouts: list[CaptionLayout]
    theme: Theme
    config: RenderConfig
    font_path: Path
    entrance: str
    scroll: ScrollLayout | None = None

    @property
    def total_frames(self) -> int:
        import math

        return max(1, math.ceil(self.audio.duration * self.config.fps - 1e-6))


class Renderer(Protocol):
    def render(self, plan: RenderPlan, output_path: Path, progress: ProgressFn | None = None) -> None: ...
