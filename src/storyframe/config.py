"""Render configuration. Everything is a plain dataclass; ``RenderConfig.from_dict`` builds one from JSON/TOML."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .exceptions import ConfigError
from .themes import Theme, get_theme

GROUPING_MODES = ("phrase", "sentence", "short_form", "word", "scroll")
ENTRANCES = ("fade", "slide_up", "pop", "word_reveal", "none")
EASINGS = ("linear", "ease_out_quad", "ease_out_cubic", "ease_in_out_cubic")
LONG_WORD_POLICIES = ("shrink", "error")


@dataclass
class GroupingOptions:
    """Overrides for the selected grouping mode; ``None`` keeps the mode default."""

    max_words: int | None = None
    max_chars: int | None = None
    max_lines: int | None = None
    max_duration: float | None = None
    max_gap: float | None = None
    break_on_punctuation: bool | None = None
    split_long_sentences: bool | None = None


@dataclass
class AnimationConfig:
    entrance: str | None = None  # None -> theme default; one of ENTRANCES ("none" = static)
    entrance_duration: float = 0.16
    exit_duration: float = 0.10
    linger: float = 0.12  # seconds a group stays after its last word before fading
    easing: str = "ease_out_cubic"
    slide_distance: float = 0.03  # fraction of frame height
    pop_start_scale: float = 0.88
    reduced_motion: bool = False  # fades only: no translation or scaling


@dataclass
class BackgroundConfig:
    style: str | None = None  # "solid" | "gradient" | None (theme default)
    image: Path | None = None  # user image, cover-fitted
    texture: bool | None = None
    vignette: bool | None = None
    animate: bool | None = None  # gentle brightness "breathing"


@dataclass
class ScrollConfig:
    """Used when grouping == "scroll": a teleprompter page that glides up as the narration advances."""

    font_scale: float = 0.62  # of the theme's font size (ignored when RenderConfig.font_size is set)
    duration: float = 0.40  # seconds for one line-advance glide (shortened if the next line starts sooner)
    easing: str = "ease_in_out_cubic"
    window_height: float = 0.78  # visible text window, fraction of frame height
    focus: float = 0.42  # where the active line sits in the window (0 = top, 1 = bottom)
    fade_edge: float = 0.20  # lines fade out over this fraction of the window at top and bottom
    break_on_sentence: bool = False  # start a new line after sentence-ending punctuation


@dataclass
class RenderConfig:
    width: int = 1080
    height: int = 1920
    fps: float = 30
    theme: str | Theme = "english_pink_story"
    theme_overrides: dict[str, Any] = field(default_factory=dict)
    grouping: str = "short_form"
    grouping_options: GroupingOptions = field(default_factory=GroupingOptions)
    highlight_active_word: bool = True
    animation: AnimationConfig = field(default_factory=AnimationConfig)
    scroll: ScrollConfig = field(default_factory=ScrollConfig)
    background: BackgroundConfig = field(default_factory=BackgroundConfig)
    font: str | None = None  # file path or font name
    font_size: int | None = None  # preferred size in px (default: theme fraction of width)
    min_font_size: int | None = None
    long_word_policy: str = "shrink"
    word_tier: str | None = None
    time_offset: float = 0.0  # seconds added to every TextGrid time to map it onto the audio timeline
    silence_labels: tuple[str, ...] | None = None
    duration_tolerance: float = 0.35
    strict_duration: bool = True
    crf: int = 18
    preset: str = "medium"
    audio_bitrate: str = "192k"
    seed: int = 0

    def __post_init__(self) -> None:
        # Accept plain dicts for nested sections: RenderConfig(animation={"entrance": "pop"})
        for key, klass in (("grouping_options", GroupingOptions), ("animation", AnimationConfig), ("scroll", ScrollConfig), ("background", BackgroundConfig)):
            val = getattr(self, key)
            if isinstance(val, dict):
                setattr(self, key, _build(klass, val, key))

    def validate(self) -> None:
        if self.width < 16 or self.height < 16 or self.width % 2 or self.height % 2:
            raise ConfigError(f"width/height must be even and >= 16 (got {self.width}x{self.height}); yuv420p needs even sizes")
        if not 1 <= self.fps <= 120:
            raise ConfigError(f"fps must be in [1, 120], got {self.fps}")
        if self.grouping not in GROUPING_MODES:
            raise ConfigError(f"grouping must be one of {GROUPING_MODES}, got {self.grouping!r}")
        a = self.animation
        if a.entrance is not None and a.entrance not in ENTRANCES:
            raise ConfigError(f"animation.entrance must be one of {ENTRANCES}, got {a.entrance!r}")
        if a.easing not in EASINGS:
            raise ConfigError(f"animation.easing must be one of {EASINGS}, got {a.easing!r}")
        if min(a.entrance_duration, a.exit_duration, a.linger) < 0:
            raise ConfigError("animation durations must be >= 0")
        if not 0.3 <= a.pop_start_scale <= 1.0:
            raise ConfigError("animation.pop_start_scale must be in [0.3, 1.0] (no overshoot beyond the layout box)")
        sc = self.scroll
        if sc.easing not in EASINGS:
            raise ConfigError(f"scroll.easing must be one of {EASINGS}")
        if not (0.2 <= sc.window_height <= 1.0 and 0 <= sc.focus <= 1 and 0 <= sc.fade_edge <= 0.5 and sc.font_scale > 0 and sc.duration >= 0):
            raise ConfigError("scroll: window_height in [0.2,1], focus in [0,1], fade_edge in [0,0.5], font_scale > 0, duration >= 0")
        if self.long_word_policy not in LONG_WORD_POLICIES:
            raise ConfigError(f"long_word_policy must be one of {LONG_WORD_POLICIES}")
        if not 0 <= self.crf <= 51:
            raise ConfigError("crf must be in [0, 51]")
        if self.duration_tolerance < 0:
            raise ConfigError("duration_tolerance must be >= 0")
        if self.background.style not in (None, "solid", "gradient"):
            raise ConfigError("background.style must be 'solid' or 'gradient'")

    def resolve_theme(self) -> Theme:
        theme = self.theme if isinstance(self.theme, Theme) else get_theme(self.theme)
        if not self.theme_overrides:
            return theme
        valid = {f.name for f in dataclasses.fields(Theme)}
        bad = set(self.theme_overrides) - valid
        if bad:
            raise ConfigError(f"unknown theme override(s): {sorted(bad)}")
        ov = {}
        for k, v in self.theme_overrides.items():
            ov[k] = tuple(v) if isinstance(v, list) else v
        return dataclasses.replace(theme, **ov)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RenderConfig":
        data = dict(data)
        nested = {"grouping_options": GroupingOptions, "animation": AnimationConfig, "scroll": ScrollConfig, "background": BackgroundConfig}
        for key, klass in nested.items():
            if key in data and isinstance(data[key], dict):
                data[key] = _build(klass, data[key], key)
        if "silence_labels" in data and data["silence_labels"] is not None:
            data["silence_labels"] = tuple(data["silence_labels"])
        cfg = _build(cls, data, "config")
        cfg.validate()
        return cfg


def _build(klass, data: dict[str, Any], where: str):
    valid = {f.name for f in dataclasses.fields(klass)}
    bad = set(data) - valid
    if bad:
        raise ConfigError(f"unknown key(s) in {where}: {sorted(bad)}; valid keys: {sorted(valid)}")
    if klass is BackgroundConfig and data.get("image") is not None:
        data = {**data, "image": Path(data["image"])}
    return klass(**data)
