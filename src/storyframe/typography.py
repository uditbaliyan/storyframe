"""Font resolution, measurement and sprite drawing (Pillow). Text is drawn once per visual state."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .exceptions import FontNotFoundError

_FONT_DIRS = [
    "/usr/share/fonts", "/usr/local/share/fonts", "/usr/share/texmf/fonts", "/Library/Fonts", "/System/Library/Fonts",
    "~/Library/Fonts", "~/.fonts", "~/.local/share/fonts", "C:/Windows/Fonts",
]
_EXTS = {".ttf", ".otf"}


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-]", "", s).lower()


@lru_cache(maxsize=1)
def _font_index() -> dict[str, Path]:
    idx: dict[str, Path] = {}
    dirs = [Path(os.path.expanduser(d)) for d in _FONT_DIRS]
    if sys.platform == "win32":
        dirs.append(Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft/Windows/Fonts")
    for d in dirs:
        if not d.is_dir():
            continue
        for p in d.rglob("*"):
            if p.suffix.lower() in _EXTS:
                idx.setdefault(_norm(p.stem), p)
    return idx


def find_font(name_or_path: str) -> Path | None:
    p = Path(os.path.expanduser(name_or_path))
    if p.is_file():
        return p
    key = _norm(Path(name_or_path).stem if p.suffix.lower() in _EXTS else name_or_path)
    return _font_index().get(key)


def resolve_font(explicit: str | None, candidates: tuple[str, ...]) -> Path:
    """Explicit font must exist (error otherwise). Theme candidates are tried in order."""
    if explicit:
        found = find_font(explicit)
        if found is None:
            raise FontNotFoundError(f"font {explicit!r} not found as a file or an installed font name. Pass a .ttf/.otf path with --font.")
        return found
    for c in candidates:
        found = find_font(c)
        if found:
            return found
    try:  # last resort: fontconfig, if present
        out = subprocess.run(["fc-match", "-f", "%{file}", "sans:bold"], capture_output=True, text=True, timeout=5).stdout.strip()
        if out and Path(out).is_file():
            return Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    raise FontNotFoundError(f"none of the theme fonts {list(candidates)} are installed. Install one or pass --font /path/to/Bold.ttf")


class FontMeasurer:
    """Caches PIL fonts per size and exposes measurements used by the layout engine."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fonts: dict[int, ImageFont.FreeTypeFont] = {}

    def font(self, size: int) -> ImageFont.FreeTypeFont:
        f = self._fonts.get(size)
        if f is None:
            try:
                f = ImageFont.truetype(str(self.path), size)
            except OSError as exc:
                raise FontNotFoundError(f"cannot load font {self.path}: {exc}") from exc
            self._fonts[size] = f
        return f

    def width(self, size: int, text: str) -> float:
        return self.font(size).getlength(text)

    def ink_extent(self, size: int) -> tuple[float, float]:
        """(ascent, descent) of actual glyph ink above/below the baseline for typical text."""
        f = self.font(size)
        top = f.getbbox("ÁHdlfbk", anchor="ls")[1]
        bottom = f.getbbox("gjpqy,", anchor="ls")[3]
        return float(-top), float(bottom)


class Sprite:
    """A rendered caption state: straight-alpha RGBA image plus cached premultiplied float arrays."""

    def __init__(self, image: Image.Image):
        self.image = image
        self._arrays: tuple[np.ndarray, np.ndarray] | None = None

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if self._arrays is None:
            a = np.asarray(self.image, dtype=np.float32)
            alpha = a[..., 3:4] / 255.0
            self._arrays = (a[..., :3] * alpha, alpha)
        return self._arrays


def _mask(size, layout, texts, indices, stroke: int, dx: float = 0.0, dy: float = 0.0, font=None) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for i in indices:
        x, y = layout.positions[i]
        kw = {"stroke_width": stroke, "stroke_fill": 255} if stroke > 0 else {}
        d.text((x + layout.pad + dx, y + layout.pad + dy), texts[i], font=font, fill=255, anchor="ls", **kw)
    return m


def _layer(size, color, mask: Image.Image, opacity: float = 1.0) -> Image.Image:
    layer = Image.new("RGBA", size, tuple(color[:3]) + (255,))
    if opacity < 1.0:
        mask = mask.point(lambda v: int(v * opacity))
    layer.putalpha(mask)
    return layer


def draw_caption(layout, texts: list[str], font: ImageFont.FreeTypeFont, theme, visible: list[bool], active: int) -> Sprite:
    """Draw visible words with theme styling: shadow/edge -> white outline -> black fill (+ accent fill)."""
    size = (layout.sprite_w, layout.sprite_h)
    idx = [i for i, v in enumerate(visible) if v]
    base = Image.new("RGBA", size, (0, 0, 0, 0))
    if idx:
        sx, sy = layout.shadow_offset
        shadow = _mask(size, layout, texts, idx, layout.stroke + layout.shadow_extra, sx, sy, font)
        if layout.shadow_blur > 0:
            shadow = shadow.filter(ImageFilter.GaussianBlur(layout.shadow_blur))
        sc = theme.shadow_color
        base = Image.alpha_composite(base, _layer(size, sc, shadow, sc[3] / 255.0))
        base = Image.alpha_composite(base, _layer(size, theme.outline, _mask(size, layout, texts, idx, layout.stroke, font=font)))
        normal = [i for i in idx if i != active]
        if normal:
            base = Image.alpha_composite(base, _layer(size, theme.fill, _mask(size, layout, texts, normal, 0, font=font)))
        if active in idx:
            base = Image.alpha_composite(base, _layer(size, theme.accent, _mask(size, layout, texts, [active], 0, font=font)))
    return Sprite(base)
