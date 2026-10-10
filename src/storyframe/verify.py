"""Post-render verification: stream layout, geometry, frame rate, duration, and a full decode pass."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .audio import find_tool, run_ffprobe
from .exceptions import MediaProbeError, OutputVerificationError


def _fps(rate: str) -> float:
    n, _, d = rate.partition("/")
    return float(n) / float(d or 1)


def verify_output(path: Path, width: int, height: int, fps: float, expected_duration: float, *, duration_tol: float = 0.15, decode: bool = True) -> dict:
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise OutputVerificationError(f"output {path} is missing or empty")
    try:
        data = run_ffprobe(path)
    except MediaProbeError as exc:
        raise OutputVerificationError(f"output is unreadable/corrupt: {exc}") from exc
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    problems = []
    if v is None:
        problems.append("no video stream")
    else:
        if (v.get("width"), v.get("height")) != (width, height):
            problems.append(f"resolution {v.get('width')}x{v.get('height')} != {width}x{height}")
        if v.get("codec_name") != "h264":
            problems.append(f"video codec {v.get('codec_name')} != h264")
        if v.get("pix_fmt") != "yuv420p":
            problems.append(f"pixel format {v.get('pix_fmt')} != yuv420p")
        if abs(_fps(v.get("r_frame_rate", "0/1")) - fps) > 0.01:
            problems.append(f"frame rate {v.get('r_frame_rate')} != {fps:g}")
    if a is None:
        problems.append("no audio stream")
    duration = float(data.get("format", {}).get("duration") or 0)
    frame_slack = 1.0 / fps
    if abs(duration - expected_duration) > duration_tol + frame_slack:
        problems.append(f"duration {duration:.3f}s differs from expected {expected_duration:.3f}s")
    if decode and not problems:
        proc = subprocess.run([find_tool("ffmpeg"), "-v", "error", "-i", str(path), "-f", "null", "-"], capture_output=True, text=True)
        if proc.returncode != 0 or proc.stderr.strip():
            problems.append(f"decode errors: {proc.stderr.strip()[:300] or 'non-zero exit'}")
    if problems:
        raise OutputVerificationError("output verification failed: " + "; ".join(problems))
    return {
        "video_codec": v["codec_name"], "pix_fmt": v["pix_fmt"], "width": v["width"], "height": v["height"],
        "fps": _fps(v["r_frame_rate"]), "audio_codec": a.get("codec_name"), "audio_sample_rate": a.get("sample_rate"),
        "audio_channels": a.get("channels"), "duration": duration, "size_bytes": path.stat().st_size,
    }
