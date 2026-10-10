"""Theme definition and registry. Themes are plain frozen dataclasses; no code runs per theme."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..exceptions import ThemeNotFoundError

Color = tuple[int, int, int]


@dataclass(frozen=True)
class BackgroundSpec:
    style: str = "gradient"  # "solid" | "gradient"
    top: Color = (255, 221, 232)
    bottom: Color = (248, 184, 208)
    light: Color = (255, 244, 248)
    light_strength: float = 0.0  # 0..1 soft radial light
    light_center: tuple[float, float] = (0.5, 0.42)
    vignette: float = 0.0  # 0..1
    texture: float = 0.0  # 0..1 fine deterministic grain
    breathe: float = 0.0  # +-fractional brightness change
    breathe_period: float = 9.0  # seconds


@dataclass(frozen=True)
class Theme:
    name: str
    description: str
    font_candidates: tuple[str, ...]
    font_size_frac: float  # preferred font size, fraction of video width
    min_font_size_frac: float
    fill: Color
    accent: Color
    outline: Color
    outline_frac: float  # outline thickness, fraction of font size
    shadow_color: tuple[int, int, int, int]
    shadow_offset_frac: tuple[float, float]  # fraction of font size
    shadow_blur_frac: float
    shadow_extra_frac: float  # extra dark edge beyond the outline
    line_spacing: float
    align: str = "center"  # left | center | right
    valign: str = "center"  # top | center | bottom
    box_width_frac: float = 0.86
    box_height_frac: float = 0.55
    box_center_y_frac: float = 0.5
    safe_margin_frac: float = 0.05
    max_lines: int = 3
    default_entrance: str = "slide_up"
    background: BackgroundSpec = field(default_factory=BackgroundSpec)


_REGISTRY: dict[str, Theme] = {}


def register_theme(theme: Theme, *, replace: bool = False) -> None:
    if theme.name in _REGISTRY and not replace:
        raise ValueError(f"theme {theme.name!r} already registered")
    _REGISTRY[theme.name] = theme


def get_theme(name: str) -> Theme:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise ThemeNotFoundError(f"unknown theme {name!r}; available: {', '.join(sorted(_REGISTRY))}") from None


def list_themes() -> list[Theme]:
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]
