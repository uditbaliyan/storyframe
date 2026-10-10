"""Command-line interface."""
from __future__ import annotations

import json
import logging
import sys
import tomllib
from pathlib import Path

import click

from . import __version__
from .api import render_preview, render_video, validate_inputs
from .config import ENTRANCES, GROUPING_MODES, RenderConfig
from .diagnostics import run_doctor
from .exceptions import ConfigError, StoryFrameError
from .themes import list_themes


def _load_config_file(path: Path) -> dict:
    try:
        raw = path.read_bytes()
        return tomllib.loads(raw.decode()) if path.suffix.lower() == ".toml" else json.loads(raw)
    except (OSError, ValueError) as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc


def _build_config(cfg_file, **opts) -> RenderConfig:
    data = _load_config_file(cfg_file) if cfg_file else {}
    for key in ("width", "height", "fps", "theme", "grouping", "font", "word_tier", "time_offset"):
        if opts.get(key) is not None:
            data[key] = opts[key]
    if opts.get("highlight") is not None:
        data["highlight_active_word"] = opts["highlight"]
    anim = dict(data.get("animation", {}))
    if opts.get("animation"):
        anim["entrance"] = opts["animation"]
    if opts.get("reduced_motion"):
        anim["reduced_motion"] = True
    if anim:
        data["animation"] = anim
    bg = dict(data.get("background", {}))
    if opts.get("background"):
        if opts["background"] in ("solid", "gradient"):
            bg["style"] = opts["background"]
        else:
            bg["image"] = opts["background"]
    if bg:
        data["background"] = bg
    return RenderConfig.from_dict(data)


def _common(f):
    for opt in reversed([
        click.option("--audio", required=True, type=click.Path(dir_okay=False), help="Narration audio file."),
        click.option("--textgrid", required=True, type=click.Path(dir_okay=False), help="MFA TextGrid for the same recording."),
        click.option("--transcript", type=click.Path(dir_okay=False), help="Optional original text (restores capitalization/punctuation)."),
        click.option("--word-tier", help="Name of the word tier (needed when detection is ambiguous)."),
        click.option("--time-offset", type=float, help="Seconds added to every TextGrid time to align it with the audio."),
        click.option("--config", "cfg_file", type=click.Path(dir_okay=False, exists=True), help="JSON or TOML RenderConfig file."),
        click.option("--verbose", "-v", is_flag=True, help="Debug logging."),
    ]):
        f = opt(f)
    return f


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


def _progress():
    last = {"k": None}

    def cb(stage: str, frac: float) -> None:
        key = (stage, int(frac * 10))
        if key != last["k"]:
            last["k"] = key
            click.echo(f"[{stage}] {frac * 100:3.0f}%", err=True)

    return cb


def _guard(fn):
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except StoryFrameError as exc:
            click.echo(f"error: {exc}", err=True)
            sys.exit(1)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@click.group()
@click.version_option(__version__, prog_name="storyframe")
def main() -> None:
    """StoryFrame: word-synchronized storytelling videos from audio + MFA TextGrid."""


@main.command()
@_common
@click.option("--output", "-o", required=True, type=click.Path(dir_okay=False), help="Output .mp4 (or .png with --preview).")
@click.option("--theme", help="Theme name (see 'storyframe themes').")
@click.option("--grouping", type=click.Choice(GROUPING_MODES))
@click.option("--width", type=int)
@click.option("--height", type=int)
@click.option("--fps", type=float)
@click.option("--font", help="Font file path or installed font name.")
@click.option("--background", help="'solid', 'gradient', or a path to a background image.")
@click.option("--animation", type=click.Choice(ENTRANCES), help="Caption entrance animation ('none' = static).")
@click.option("--reduced-motion", is_flag=True, help="Fades only; no sliding or scaling.")
@click.option("--highlight/--no-highlight", default=None, help="Active-word highlighting (default on).")
@click.option("--preview", type=float, metavar="SECONDS", help="Write one PNG of the frame at SECONDS instead of a video.")
@click.option("--dry-run", is_flag=True, help="Validate, group and lay out; do not render.")
@click.option("--overwrite", is_flag=True, help="Replace an existing output file.")
@_guard
def render(audio, textgrid, transcript, word_tier, time_offset, cfg_file, verbose, output, theme, grouping, width, height, fps, font, background, animation, reduced_motion, highlight, preview, dry_run, overwrite):
    """Render the video."""
    _setup_logging(verbose)
    cfg = _build_config(cfg_file, word_tier=word_tier, time_offset=time_offset, theme=theme, grouping=grouping, width=width, height=height, fps=fps, font=font, background=background, animation=animation, reduced_motion=reduced_motion, highlight=highlight)
    if preview is not None:
        p = render_preview(audio, textgrid, output, preview, cfg, transcript, overwrite=overwrite)
        click.echo(f"wrote preview frame: {p}")
        return
    res = render_video(audio, textgrid, output, cfg, transcript, overwrite=overwrite, dry_run=dry_run, progress=_progress())
    for w in res.warnings:
        click.echo(f"warning: {w}", err=True)
    if res.dry_run:
        click.echo(f"dry run OK: {res.num_words} words -> {res.num_groups} caption groups, {res.frames} frames at {res.fps:g} fps, {res.resolution[0]}x{res.resolution[1]}")
    else:
        click.echo(f"wrote {res.output_path} ({res.duration:.2f}s, {res.resolution[0]}x{res.resolution[1]} @ {res.fps:g} fps, {res.render_seconds:.1f}s to render)")


@main.command()
@_common
@_guard
def validate(audio, textgrid, transcript, word_tier, time_offset, cfg_file, verbose):
    """Validate audio + TextGrid (+ transcript) without rendering."""
    _setup_logging(verbose)
    cfg = _build_config(cfg_file, word_tier=word_tier, time_offset=time_offset)
    report = validate_inputs(audio, textgrid, cfg, transcript)
    click.echo(report.format())
    sys.exit(0 if report.ok else 1)


@main.command()
def themes() -> None:
    """List built-in themes."""
    for t in list_themes():
        click.echo(f"{t.name:22s} {t.description}")


@main.command()
@click.option("--output-dir", type=click.Path(file_okay=False), help="Directory whose write permission to check (default: cwd).")
def doctor(output_dir) -> None:
    """Check the environment (FFmpeg, fonts, dependencies)."""
    failed = False
    for c in run_doctor(Path(output_dir) if output_dir else None):
        tag = {"ok": "OK  ", "warn": "WARN", "fail": "FAIL"}[c.status]
        click.echo(f"[{tag}] {'(required)' if c.required else '(optional)'} {c.name}: {c.detail}")
        failed |= c.status == "fail" and c.required
    sys.exit(1 if failed else 0)
