"""`storyframe doctor`: environment checks. Required and optional dependencies are labelled separately."""
from __future__ import annotations

import importlib.metadata as md
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str
    required: bool = True


def _ver(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def run_doctor(output_dir: Path | None = None) -> list[Check]:
    from .themes import list_themes
    from .typography import find_font, resolve_font
    from .exceptions import FontNotFoundError

    checks: list[Check] = []
    v = sys.version_info
    checks.append(Check("Python >= 3.11", "ok" if v >= (3, 11) else "fail", platform.python_version()))
    checks.append(Check("storyframe package", "ok" if _ver("storyframe") else "warn", _ver("storyframe") or "not installed as a distribution (running from source?)", required=False))
    for pkg in ("Pillow", "numpy", "praatio", "click"):
        ver = _ver(pkg)
        checks.append(Check(f"Python dependency: {pkg}", "ok" if ver else "fail", ver or "NOT INSTALLED"))
    for tool in ("ffmpeg", "ffprobe"):
        exe = shutil.which(tool)
        if not exe:
            checks.append(Check(tool, "fail", "not found on PATH"))
            continue
        out = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.splitlines()
        checks.append(Check(tool, "ok", (out[0] if out else exe)))
    if shutil.which("ffmpeg"):
        enc = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        for name, label in (("libx264", "H.264 encoder (libx264)"), ("aac ", "AAC audio encoder")):
            checks.append(Check(label, "ok" if f" {name.strip()} " in enc or name in enc else "fail", "available" if name in enc else "missing from this FFmpeg build"))
    try:
        for t in list_themes():
            try:
                p = resolve_font(None, t.font_candidates)
                best = find_font(t.font_candidates[0]) is not None
                checks.append(Check(f"font for theme {t.name}", "ok" if best else "warn", f"{p.name}" + ("" if best else f" (fallback; preferred {t.font_candidates[0]} not installed)"), required=False))
            except FontNotFoundError as exc:
                checks.append(Check(f"font for theme {t.name}", "fail", str(exc)))
    except Exception as exc:  # pragma: no cover
        checks.append(Check("themes", "fail", str(exc)))
    d = Path(output_dir) if output_dir else Path.cwd()
    ok = d.is_dir() and os.access(d, os.W_OK)
    if ok:
        try:
            with tempfile.NamedTemporaryFile(dir=d):
                pass
        except OSError:
            ok = False
    checks.append(Check(f"output directory writable ({d})", "ok" if ok else "fail", "writable" if ok else "not writable or missing"))
    return checks
