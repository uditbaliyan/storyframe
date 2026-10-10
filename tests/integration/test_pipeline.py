import os
import shutil
import subprocess
import sys

import numpy as np
import pytest
from PIL import Image

from conftest import running_as_root
from storyframe import RenderConfig, render_video, validate_inputs, render_preview
from storyframe.api import _prepare
from storyframe.exceptions import (FFmpegNotFoundError, FontNotFoundError, InputFileError, OutputExistsError, OutputVerificationError, RenderError, StoryFrameError, TextGridError)
from storyframe.renderers.base import RenderPlan
from storyframe.renderers.compositor import FrameCompositor
from storyframe.verify import verify_output

pytestmark = pytest.mark.integration
SMALL = dict(width=360, height=640, fps=30)  # keeps CI fast; layout is resolution-relative


def probe(path):
    import json
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


@pytest.fixture
def rendered(media, tmp_path):
    out = tmp_path / "story.mp4"
    cfg = RenderConfig(**SMALL)
    res = render_video(media["audio"], media["textgrid"], out, cfg, media["transcript"])
    return out, res, cfg


def test_end_to_end_mp4_streams_and_geometry(rendered, media):
    out, res, cfg = rendered
    assert out.exists() and out.stat().st_size > 10_000
    info = probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"], v["codec_name"], v["pix_fmt"], v["r_frame_rate"]) == (360, 640, "h264", "yuv420p", "30/1")
    assert a["codec_name"] == "aac" and a["sample_rate"] == "24000" and a["channels"] == 1  # source layout preserved
    assert abs(float(info["format"]["duration"]) - 11.32) < 0.1
    assert res.frames == 340 and res.resolution == (360, 640) and res.verification["video_codec"] == "h264"


def test_audio_content_preserved(rendered, media, tmp_path):
    out, *_ = rendered
    def pcm(p):
        return np.frombuffer(subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-f", "s16le", "-ac", "1", "-ar", "24000", "-"], capture_output=True, check=True).stdout, np.int16).astype(np.float32)
    a, b = pcm(media["audio"]), pcm(out)
    n = min(len(a), len(b))
    assert abs(len(a) - len(b)) < 24000 * 0.1
    # tone-burst envelopes must line up: correlate short-time energy (lossy AAC, so compare envelopes)
    env = lambda x: np.convolve(np.abs(x[:n]), np.ones(2400) / 2400, "same")
    assert np.corrcoef(env(a), env(b))[0, 1] > 0.95


def test_caption_visible_and_inside_frame_in_decoded_video(rendered, media, tmp_path):
    out, res, cfg = rendered
    png = tmp_path / "f.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.2", "-i", str(out), "-frames:v", "1", str(png)], check=True)
    im = np.asarray(Image.open(png).convert("RGB")).astype(int)
    dark = (im.max(axis=2) < 70)
    assert dark.sum() > 300, "caption fill not visible"
    ys, xs = np.nonzero(dark)
    mx, my = int(0.05 * 360), int(0.05 * 640)
    assert xs.min() >= mx and xs.max() <= 360 - mx and ys.min() >= my and ys.max() <= 640 - my
    blank = tmp_path / "b.png"  # before the first word (0.35s): no caption
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "0.1", "-i", str(out), "-frames:v", "1", str(blank)], check=True)
    assert (np.asarray(Image.open(blank).convert("RGB")).max(axis=2) < 70).sum() == 0


def _compositor(media, **kw):
    cfg = RenderConfig(**SMALL, **kw)
    prep = _prepare(media["audio"], media["textgrid"], cfg, media["transcript"])
    plan = RenderPlan(prep.audio, prep.groups, prep.layouts, prep.theme, cfg, prep.font_path, prep.entrance)
    return FrameCompositor(plan), prep


def _accent_cols(frame, accent):
    m = (np.abs(frame.astype(int) - np.array(accent)).sum(axis=2) < 60)
    if not m.any():
        return None
    xs = np.nonzero(m.any(axis=0))[0]
    return xs.min(), xs.max()


def test_active_word_highlight_follows_mfa_intervals(media):
    comp, prep = _compositor(media)
    accent = prep.theme.accent
    checked = 0
    for gi, (g, lay) in enumerate(zip(prep.groups, prep.layouts)):
        for wi, w in enumerate(g.words):
            t = (w.start + w.end) / 2
            frame = comp.frame_at(t)
            cols = _accent_cols(frame, accent)
            x0, _, x1, _ = lay.word_box(wi)
            assert cols is not None, f"no highlight for {w.text!r} at {t:.2f}s"
            assert cols[0] >= x0 - 2 and cols[1] <= x1 + 2, f"highlight for {w.text!r} outside its word box"
            checked += 1
    assert checked == 23


def test_highlight_switches_exactly_at_word_boundary(media):
    comp, prep = _compositor(media)
    g = prep.groups[0]
    w0, w1 = g.words[0], g.words[1]
    boundary = w0.end  # word 0 ends, word 1 starts after a 30 ms MFA gap
    assert comp.caption_state(boundary - 0.001)[1] == 0
    assert comp.caption_state(boundary + 0.001)[1] == -1  # inside the gap: nothing invented
    assert comp.caption_state(w1.start + 0.001)[1] == 1


def test_highlight_independent_of_animation_choice(media):
    """Entrance animation changes alpha/offset only: the active word at any instant inside an MFA word
    interval is identical for every animation style."""
    probe_times = None
    results = []
    for ent in ("fade", "slide_up", "pop", "word_reveal", "none"):
        comp, prep = _compositor(media, animation={"entrance": ent})
        probe_times = probe_times or [(w.start + w.end) / 2 for g in prep.groups for w in g.words]
        results.append([comp.caption_state(t)[:2] for t in probe_times])
    assert all(r == results[0] for r in results)


def test_highlight_disabled(media):
    comp, prep = _compositor(media, highlight_active_word=False)
    frame = comp.frame_at(1.0)
    assert _accent_cols(frame, prep.theme.accent) is None


def test_no_caption_in_genuine_gap(media):
    comp, prep = _compositor(media)
    gaps = [(a.visible_end, b.start) for a, b in zip(prep.groups, prep.groups[1:]) if b.start - a.visible_end > 0.05]
    assert gaps, "fixture should contain a sentence pause longer than linger+fade"
    t = (gaps[0][0] + gaps[0][1]) / 2
    assert comp.caption_state(t) is None


def test_rendering_is_deterministic(media):
    c1, _ = _compositor(media)
    c2, _ = _compositor(media)
    for t in (0.2, 1.3, 5.5):
        assert np.array_equal(c1.frame_at(t), c2.frame_at(t))


def test_preview_png(media, tmp_path):
    p = render_preview(media["audio"], media["textgrid"], tmp_path / "p.png", 1.2, RenderConfig(**SMALL), media["transcript"])
    assert Image.open(p).size == (360, 640)


def test_word_reveal_shows_only_spoken_words(media):
    comp, prep = _compositor(media, animation={"entrance": "word_reveal"})
    g = prep.groups[0]
    t0 = g.words[0].start + 0.3
    assert comp.caption_state(t0)[2] == 1 and comp.caption_state(g.end - 0.001)[2] == len(g.words)


def test_validate_only_and_dry_run(media, tmp_path):
    rep = validate_inputs(media["audio"], media["textgrid"], transcript_path=media["transcript"])
    assert rep.ok and "word tier" in rep.info
    res = render_video(media["audio"], media["textgrid"], tmp_path / "never.mp4", RenderConfig(**SMALL), dry_run=True)
    assert res.dry_run and not (tmp_path / "never.mp4").exists() and res.num_groups > 3


# ---- error paths -------------------------------------------------------------------------------------------------
def test_missing_inputs(media, tmp_path):
    with pytest.raises(InputFileError):
        render_video(tmp_path / "no.wav", media["textgrid"], tmp_path / "o.mp4")
    with pytest.raises(InputFileError):
        render_video(media["audio"], tmp_path / "no.TextGrid", tmp_path / "o.mp4")
    rep = validate_inputs(tmp_path / "no.wav", media["textgrid"])
    assert not rep.ok and "not found" in rep.errors[0]


def test_malformed_textgrid_and_wrong_audio_duration(media, tmp_path, make_tg, items):
    bad = tmp_path / "bad.TextGrid"
    bad.write_text("garbage")
    with pytest.raises(TextGridError):
        render_video(media["audio"], bad, tmp_path / "o.mp4")
    short = make_tg([("hello", 0.0, 0.5)], 0.6, name="short.TextGrid")
    rep = validate_inputs(media["audio"], short)
    assert not rep.ok and "differs" in rep.errors[0]
    ok = validate_inputs(media["audio"], short, RenderConfig(strict_duration=False))
    assert ok.ok and ok.warnings


def test_time_offset_fixes_trimmed_alignment(media, tmp_path):
    import make_fixtures as mf
    items, total = mf.build_timing()
    cut = next(s for l, s, e in items if l == "every") - 0.1  # TextGrid made from audio trimmed at `cut`
    trimmed = [(l, round(s - cut, 3), round(e - cut, 3)) for l, s, e in items if s >= cut]
    tg = tmp_path / "trimmed.TextGrid"
    tg.write_text(mf.textgrid_text(trimmed, round(total - cut, 3)))
    rep = validate_inputs(media["audio"], tg)  # full recording + trimmed alignment: must not pass silently
    assert not rep.ok and "--time-offset" in rep.errors[0]
    assert validate_inputs(media["audio"], tg, RenderConfig(time_offset=cut)).ok


def test_existing_output_protected(media, tmp_path):
    out = tmp_path / "o.mp4"
    out.write_bytes(b"precious")
    with pytest.raises(OutputExistsError):
        render_video(media["audio"], media["textgrid"], out, RenderConfig(**SMALL))
    assert out.read_bytes() == b"precious"
    render_video(media["audio"], media["textgrid"], out, RenderConfig(**SMALL), overwrite=True)
    assert out.stat().st_size > 1000


@pytest.mark.skipif(running_as_root(), reason="root ignores directory permissions; unwritable-path test needs a non-root user")
def test_unwritable_output_dir(media, tmp_path):
    d = tmp_path / "ro"
    d.mkdir()
    d.chmod(0o500)
    try:
        with pytest.raises(InputFileError, match="not writable"):
            render_video(media["audio"], media["textgrid"], d / "o.mp4", RenderConfig(**SMALL))
    finally:
        d.chmod(0o700)


def test_output_path_with_spaces(media, tmp_path):
    out = tmp_path / "my story folder" / "final cut.mp4"
    render_video(media["audio"], media["textgrid"], out, RenderConfig(**SMALL))
    assert out.exists()


def test_missing_font(media, tmp_path):
    with pytest.raises(FontNotFoundError):
        render_video(media["audio"], media["textgrid"], tmp_path / "o.mp4", RenderConfig(font="/nope/Missing.ttf", **SMALL))


def test_missing_ffmpeg(media, tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name, *a, **k: None)
    with pytest.raises(FFmpegNotFoundError, match="Install FFmpeg"):
        render_video(media["audio"], media["textgrid"], tmp_path / "o.mp4", RenderConfig(**SMALL))


def test_interrupted_render_leaves_nothing_behind(media, tmp_path, monkeypatch):
    calls = {"n": 0}
    orig = FrameCompositor.frame_at

    def boom(self, t):
        calls["n"] += 1
        if calls["n"] > 20:
            raise KeyboardInterrupt
        return orig(self, t)

    monkeypatch.setattr(FrameCompositor, "frame_at", boom)
    out = tmp_path / "o.mp4"
    with pytest.raises(KeyboardInterrupt):
        render_video(media["audio"], media["textgrid"], out, RenderConfig(**SMALL))
    assert not out.exists() and not list(tmp_path.glob(".storyframe-*"))


def test_encoder_failure_reports_ffmpeg_output(media, tmp_path):
    with pytest.raises(RenderError, match="ffmpeg exited"):
        render_video(media["audio"], media["textgrid"], tmp_path / "o.mp4", RenderConfig(preset="not-a-preset", **SMALL))
    assert not list(tmp_path.glob(".storyframe-*"))


def test_corrupt_and_truncated_output_detected(rendered, tmp_path):
    out, res, cfg = rendered
    trunc = tmp_path / "trunc.mp4"
    trunc.write_bytes(out.read_bytes()[: out.stat().st_size // 3])
    with pytest.raises(OutputVerificationError):
        verify_output(trunc, 360, 640, 30, res.duration)
    junk = tmp_path / "junk.mp4"
    junk.write_bytes(b"\x00" * 4096)
    with pytest.raises(OutputVerificationError):
        verify_output(junk, 360, 640, 30, res.duration)
    with pytest.raises(OutputVerificationError):
        verify_output(tmp_path / "missing.mp4", 360, 640, 30, 1.0)
    with pytest.raises(OutputVerificationError, match="resolution"):
        verify_output(out, 720, 1280, 30, res.duration)


def test_cli_roundtrip(media, tmp_path):
    out = tmp_path / "cli.mp4"
    base = [sys.executable, "-m", "storyframe.cli"]
    r = subprocess.run(["storyframe", "render", "--audio", str(media["audio"]), "--textgrid", str(media["textgrid"]), "--transcript", str(media["transcript"]), "-o", str(out), "--width", "360", "--height", "640", "--theme", "english_pink_story"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    again = subprocess.run(["storyframe", "render", "--audio", str(media["audio"]), "--textgrid", str(media["textgrid"]), "-o", str(out)], capture_output=True, text=True)
    assert again.returncode == 1 and "already exists" in again.stderr
    v = subprocess.run(["storyframe", "validate", "--audio", str(media["audio"]), "--textgrid", str(media["textgrid"])], capture_output=True, text=True)
    assert v.returncode == 0 and "RESULT: OK" in v.stdout
    assert subprocess.run(["storyframe", "themes"], capture_output=True, text=True).stdout.count("\n") >= 3
    assert subprocess.run(["storyframe", "doctor"], capture_output=True, text=True).returncode == 0


# ---- scroll mode ---------------------------------------------------------------------------------------------
def _scroll_comp(long_media, **kw):
    cfg = RenderConfig(width=640, height=360, grouping="scroll", **kw)
    prep = _prepare(long_media["audio"], long_media["textgrid"], cfg, long_media["transcript"])
    return FrameCompositor(prep.plan()), prep


def test_scroll_highlight_on_every_word_and_inside_safe_area(long_media):
    comp, prep = _scroll_comp(long_media)
    th = prep.theme
    for w in prep.scroll.words:
        t = (w.start + w.end) / 2
        f = comp.frame_at(t)
        cols = _accent_cols(f, th.accent)
        assert cols is not None, f"no highlight for {w.text!r} at {t:.2f}s"
        m = (np.abs(f.astype(int) - np.array(th.accent)).sum(axis=2) < 60)
        ys = np.nonzero(m.any(axis=1))[0]
        assert ys.min() >= 0.05 * 360 and ys.max() <= 0.95 * 360  # highlighted word is inside the safe region
        assert cols[0] >= 0.05 * 640 and cols[1] <= 0.95 * 640


def test_scroll_moves_up_and_text_fades_not_clips(long_media):
    comp, prep = _scroll_comp(long_media)
    sl = prep.scroll
    k = len(sl.lines) // 2
    t_before, t_after = sl.triggers[k] - 0.01, sl.triggers[k] + 0.6
    a, b = comp.frame_at(t_before).astype(int), comp.frame_at(t_after).astype(int)
    assert np.abs(a - b).sum() > 0
    top = lambda f: np.nonzero((f.max(axis=2) < 70).any(axis=1))[0].min()
    # dark text never reaches the frame edge rows (fade zone + safe margins)
    for f in (a, b):
        rows = np.nonzero((f.max(axis=2) < 70).any(axis=1))[0]
        assert rows.min() >= 0.05 * 360 and rows.max() <= 0.95 * 360


def test_scroll_nothing_before_first_word_or_long_after_end(long_media):
    comp, prep = _scroll_comp(long_media)
    w = prep.scroll.words
    assert (comp.frame_at(w[0].start - 0.5).max(axis=2) < 70).sum() == 0
    assert (comp.frame_at(w[-1].end + 1.5).max(axis=2) < 70).sum() == 0


def test_scroll_end_to_end_mp4(long_media, tmp_path):
    out = tmp_path / "scroll.mp4"
    res = render_video(long_media["audio"], long_media["textgrid"], out, RenderConfig(width=640, height=360, grouping="scroll", fps=24), long_media["transcript"])
    assert res.verification["width"] == 640 and res.num_groups > 8 and out.stat().st_size > 10_000
