"""Public API: ``render_video``, ``validate_inputs``, ``render_preview``."""
from __future__ import annotations

import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .adapters.mfa_textgrid import read_textgrid
from .audio import probe_audio
from .config import RenderConfig
from .exceptions import InputFileError, OutputExistsError, StoryFrameError
from .grouping import group_words, resolve_params
from .layout import CaptionLayout, LayoutEngine, ScrollLayout, build_scroll
from .models import AlignmentData, CaptionGroup, MediaInfo, RenderResult, ValidationReport, Word
from .renderers.base import RenderPlan
from .renderers.compositor import FrameCompositor
from .renderers.ffmpeg import FFmpegRenderer
from .themes import Theme
from .timeline import apply_offset, schedule_groups
from .typography import resolve_font
from .validation import apply_transcript, check_duration
from .verify import verify_output

log = logging.getLogger("storyframe")
ProgressFn = Callable[[str, float], None]
PathLike = str | os.PathLike


@dataclass
class Prepared:
    audio: MediaInfo
    alignment: AlignmentData
    words: list[Word]
    theme: Theme
    config: RenderConfig
    warnings: list[str] = field(default_factory=list)
    groups: list[CaptionGroup] = field(default_factory=list)
    layouts: list[CaptionLayout] = field(default_factory=list)
    font_path: Path | None = None
    entrance: str = "none"
    scroll: ScrollLayout | None = None

    def plan(self) -> RenderPlan:
        return RenderPlan(self.audio, self.groups, self.layouts, self.theme, self.config, self.font_path, self.entrance, self.scroll)

    @property
    def num_groups(self) -> int:
        return len(self.scroll.lines) if self.scroll else len(self.groups)


def _require_file(path: PathLike, what: str) -> Path:
    p = Path(path)
    if not p.is_file():
        raise InputFileError(f"{what} not found: {p}")
    if p.stat().st_size == 0:
        raise InputFileError(f"{what} is empty: {p}")
    return p


def _prepare(audio_path, textgrid_path, config: RenderConfig, transcript_path=None, *, layout: bool = True, progress: ProgressFn | None = None) -> Prepared:
    config.validate()
    theme = config.resolve_theme()
    audio_p = _require_file(audio_path, "audio file")
    tg_p = _require_file(textgrid_path, "TextGrid file")
    tr_p = _require_file(transcript_path, "transcript file") if transcript_path else None

    def tick(stage, f=1.0):
        if progress:
            progress(stage, f)

    audio = probe_audio(audio_p)
    tick("probe")
    alignment = read_textgrid(tg_p, word_tier=config.word_tier, silence_labels=config.silence_labels)
    tick("parse")
    warnings = list(alignment.warnings)
    words = apply_offset(alignment.words, config.time_offset)
    check_duration(words, alignment.xmax, config.time_offset, audio.duration, config.duration_tolerance, config.strict_duration, warnings)
    if tr_p is not None:
        words = apply_transcript(words, tr_p.read_text(encoding="utf-8"))
    tick("validate")
    prep = Prepared(audio, alignment, words, theme, config, warnings)
    if not layout:
        return prep

    if config.grouping == "scroll":
        prep.font_path = resolve_font(config.font, theme.font_candidates)
        prep.scroll = build_scroll(words, theme, config, prep.font_path)
        tick("layout")
        return prep

    params = resolve_params(config.grouping, config.grouping_options)
    groups = group_words(words, params)
    font_path = resolve_font(config.font, theme.font_candidates)
    engine = LayoutEngine(theme, config, font_path, max_lines=config.grouping_options.max_lines)
    fitted = engine.fit_groups(groups, warnings)
    entrance = config.animation.entrance or theme.default_entrance
    scheduled = schedule_groups([g for g, _ in fitted], config.animation.linger, config.animation.exit_duration, fade_exit=entrance != "none")
    prep.groups, prep.layouts = scheduled, [l for _, l in fitted]
    prep.font_path, prep.entrance = font_path, entrance
    tick("layout")
    return prep


def validate_inputs(audio_path: PathLike, textgrid_path: PathLike, config: RenderConfig | None = None, transcript_path: PathLike | None = None, *, check_layout: bool = False) -> ValidationReport:
    """Validate inputs without rendering. Never raises StoryFrameError; problems land in ``report.errors``."""
    config = config or RenderConfig()
    report = ValidationReport()
    try:
        prep = _prepare(audio_path, textgrid_path, config, transcript_path, layout=check_layout)
    except StoryFrameError as exc:
        report.errors.append(str(exc))
        return report
    a, al = prep.audio, prep.alignment
    report.info.update({
        "audio duration": f"{a.duration:.3f}s ({a.audio_codec}, {a.sample_rate} Hz, {a.channels} ch)",
        "TextGrid tiers": ", ".join(repr(n) for n in al.tier_names),
        "word tier": repr(al.tier_name),
        "TextGrid span": f"{al.xmin:.3f}s - {al.xmax:.3f}s",
        "words": f"{len(prep.words)} ({prep.words[0].start:.3f}s - {prep.words[-1].end:.3f}s on the audio timeline)",
        "time offset": f"{config.time_offset:+.3f}s",
        "transcript": "matched" if transcript_path else "not supplied",
    })
    if check_layout:
        report.info["caption groups" if not prep.scroll else "scroll lines"] = prep.num_groups
    report.warnings.extend(prep.warnings)
    return report


def _check_output(output_path: PathLike, overwrite: bool) -> Path:
    out = Path(output_path)
    if out.exists() and not overwrite:
        raise OutputExistsError(f"{out} already exists; pass overwrite=True (--overwrite) to replace it")
    parent = out.parent if str(out.parent) else Path(".")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InputFileError(f"cannot create output directory {parent}: {exc}") from exc
    if not os.access(parent, os.W_OK):
        raise InputFileError(f"output directory is not writable: {parent}")
    return out


def render_video(audio_path: PathLike, textgrid_path: PathLike, output_path: PathLike, config: RenderConfig | None = None, transcript_path: PathLike | None = None, *, overwrite: bool = False, dry_run: bool = False, progress: ProgressFn | None = None) -> RenderResult:
    """Render the narrated, word-synchronized video. Validates everything before encoding starts."""
    t0 = time.monotonic()
    config = config or RenderConfig()
    out = _check_output(output_path, overwrite) if not dry_run else Path(output_path)
    prep = _prepare(audio_path, textgrid_path, config, transcript_path, progress=progress)
    plan = prep.plan()
    expected = plan.total_frames / config.fps
    base = dict(duration=expected, resolution=(config.width, config.height), fps=config.fps, frames=plan.total_frames, num_words=len(prep.words), num_groups=prep.num_groups, warnings=prep.warnings)
    if dry_run:
        return RenderResult(output_path=None, render_seconds=time.monotonic() - t0, verification={}, dry_run=True, **base)

    fd, tmp_name = tempfile.mkstemp(prefix=".storyframe-", suffix=".mp4", dir=out.parent)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        FFmpegRenderer().render(plan, tmp, progress)
        if progress:
            progress("verify", 0.0)
        info = verify_output(tmp, config.width, config.height, config.fps, expected)
        os.replace(tmp, out)
        if progress:
            progress("verify", 1.0)
    finally:
        tmp.unlink(missing_ok=True)
    return RenderResult(output_path=out, render_seconds=time.monotonic() - t0, verification=info, **base)


def render_preview(audio_path: PathLike, textgrid_path: PathLike, output_png: PathLike, at: float, config: RenderConfig | None = None, transcript_path: PathLike | None = None, *, overwrite: bool = False) -> Path:
    """Write a single PNG of the frame shown at ``at`` seconds (no FFmpeg encode needed)."""
    from PIL import Image

    config = config or RenderConfig()
    out = _check_output(output_png, overwrite)
    prep = _prepare(audio_path, textgrid_path, config, transcript_path)
    plan = prep.plan()
    Image.fromarray(FrameCompositor(plan).frame_at(at)).save(out)
    return out
