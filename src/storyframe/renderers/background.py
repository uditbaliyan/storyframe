"""Procedural, deterministic backgrounds. Built once per render; per-frame cost is a cached brightness LUT."""
from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import numpy as np
from PIL import Image

from ..config import BackgroundConfig
from ..exceptions import InputFileError
from ..themes.registry import BackgroundSpec


def effective_spec(spec: BackgroundSpec, bg: BackgroundConfig, has_image: bool) -> BackgroundSpec:
    ch: dict = {}
    if bg.style:
        ch["style"] = bg.style
    if bg.texture is False:
        ch["texture"] = 0.0
    if bg.vignette is False:
        ch["vignette"] = 0.0
    if bg.animate is False or has_image:
        ch["breathe"] = 0.0
    return dataclasses.replace(spec, **ch) if ch else spec


def _image_background(path: Path, w: int, h: int) -> np.ndarray:
    if not Path(path).is_file():
        raise InputFileError(f"background image not found: {path}")
    try:
        img = Image.open(path).convert("RGB")
    except Exception as exc:
        raise InputFileError(f"cannot read background image {path}: {exc}") from exc
    s = max(w / img.width, h / img.height)
    img = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    l, t = (img.width - w) // 2, (img.height - h) // 2
    return np.asarray(img.crop((l, t, l + w, t + h)), dtype=np.uint8).copy()


def build_background(spec: BackgroundSpec, bg: BackgroundConfig, w: int, h: int, seed: int) -> tuple[np.ndarray, BackgroundSpec]:
    spec = effective_spec(spec, bg, bg.image is not None)
    if bg.image is not None:
        return _image_background(bg.image, w, h), spec
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    top = np.array(spec.top, np.float32)
    bot = np.array(spec.bottom, np.float32)
    img = (top * (1 - y) + bot * y) if spec.style == "gradient" else np.broadcast_to(top, (h, 1, 3))
    img = np.broadcast_to(img, (h, w, 3)).astype(np.float32).copy()
    if spec.light_strength > 0 or spec.vignette > 0:
        xs = (np.linspace(0, 1, w, dtype=np.float32) - spec.light_center[0])[None, :]
        ys = (np.linspace(0, 1, h, dtype=np.float32) - spec.light_center[1])[:, None] * (h / w)
        d2 = xs ** 2 + ys ** 2
        if spec.light_strength > 0:
            k = (spec.light_strength * np.exp(-d2 / 0.18))[..., None]
            img += (np.array(spec.light, np.float32) - img) * k
        if spec.vignette > 0:
            cx = (np.linspace(0, 1, w, dtype=np.float32) - 0.5)[None, :]
            cy = (np.linspace(0, 1, h, dtype=np.float32) - 0.5)[:, None] * (h / w)
            r2 = cx ** 2 + cy ** 2
            img *= (1 - spec.vignette * np.clip(r2 / 0.6, 0, 1) ** 1.5)[..., None]
    rng = np.random.default_rng(seed)  # deterministic grain / dither
    sigma = max(spec.texture * 255.0, 0.35)
    img += rng.normal(0, sigma, (h, w, 1)).astype(np.float32)
    return np.clip(img + 0.5, 0, 255).astype(np.uint8), spec


def breathe_gain(spec: BackgroundSpec, t: float) -> float:
    if spec.breathe <= 0:
        return 1.0
    return 1.0 + spec.breathe * math.sin(2 * math.pi * t / spec.breathe_period)
