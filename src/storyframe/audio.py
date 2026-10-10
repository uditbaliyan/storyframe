"""ffprobe wrappers and tool discovery."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from .exceptions import FFmpegNotFoundError, InputFileError, MediaProbeError
from .models import MediaInfo


def find_tool(name: str) -> str:
    exe = shutil.which(name)
    if not exe:
        raise FFmpegNotFoundError(
            f"{name!r} not found on PATH. Install FFmpeg (https://ffmpeg.org/download.html; "
            f"e.g. 'apt install ffmpeg', 'brew install ffmpeg', 'winget install ffmpeg') and re-run 'storyframe doctor'."
        )
    return exe


def run_ffprobe(path: Path) -> dict:
    cmd = [find_tool("ffprobe"), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaProbeError(f"ffprobe could not read {path}: {proc.stderr.strip() or 'unknown error'}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise MediaProbeError(f"ffprobe returned unparsable output for {path}") from exc


def probe_audio(path: str | Path) -> MediaInfo:
    path = Path(path)
    if not path.is_file():
        raise InputFileError(f"audio file not found: {path}")
    data = run_ffprobe(path)
    audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if audio is None:
        raise MediaProbeError(f"{path} contains no audio stream")
    dur = audio.get("duration") or data.get("format", {}).get("duration")
    try:
        duration = float(dur)
    except (TypeError, ValueError):
        raise MediaProbeError(f"cannot determine audio duration of {path}") from None
    if duration <= 0:
        raise MediaProbeError(f"audio duration of {path} is not positive ({duration})")
    return MediaInfo(
        path=path,
        duration=duration,
        audio_codec=audio.get("codec_name"),
        sample_rate=int(audio["sample_rate"]) if audio.get("sample_rate") else None,
        channels=int(audio["channels"]) if audio.get("channels") else None,
    )
