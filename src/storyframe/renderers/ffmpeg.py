"""Primary renderer: composited raw RGB frames are streamed to FFmpeg stdin and muxed with the narration.
Only one frame is held in memory; nothing is written to disk except the encoder log and the MP4."""
from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path

from ..audio import find_tool
from ..exceptions import RenderError
from .base import ProgressFn, RenderPlan
from .compositor import FrameCompositor

log = logging.getLogger("storyframe")


def build_command(plan: RenderPlan, output_path: Path) -> list[str]:
    c = plan.config
    return [
        find_tool("ffmpeg"), "-hide_banner", "-loglevel", "warning", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{c.width}x{c.height}", "-framerate", f"{c.fps:g}", "-i", "pipe:0",
        "-i", str(plan.audio.path),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", c.preset, "-crf", str(c.crf), "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
        "-g", str(max(1, round(c.fps * 2))),
        "-c:a", "aac", "-b:a", c.audio_bitrate,
        "-movflags", "+faststart", "-f", "mp4", str(output_path),
    ]


class FFmpegRenderer:
    def render(self, plan: RenderPlan, output_path: Path, progress: ProgressFn | None = None) -> None:
        comp = FrameCompositor(plan)
        total = plan.total_frames
        cmd = build_command(plan, output_path)
        log.debug("ffmpeg command: %s", cmd)
        with tempfile.TemporaryFile(mode="w+b") as errlog:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=errlog)
            try:
                step = max(1, total // 100)
                for n in range(total):
                    proc.stdin.write(memoryview(comp.frame_at(comp.sample_time(n))))
                    if progress and (n % step == 0 or n == total - 1):
                        progress("render", (n + 1) / total)
                proc.stdin.close()
                rc = proc.wait()
            except BrokenPipeError:
                rc = proc.wait()
            except BaseException:
                proc.kill()
                proc.wait()
                raise
            if rc != 0:
                errlog.seek(0)
                tail = errlog.read()[-2000:].decode("utf-8", "replace").strip()
                raise RenderError(f"ffmpeg exited with status {rc}:\n{tail}")
