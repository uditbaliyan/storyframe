import pytest

from storyframe.adapters.mfa_textgrid import read_textgrid
from storyframe.config import RenderConfig
from storyframe.exceptions import ConfigError, LayoutError
from storyframe.layout import build_scroll
from storyframe.models import Word
from storyframe.typography import resolve_font
import make_fixtures as mf


def build(long_media, **kw):
    cfg = RenderConfig(width=1920, height=1080, grouping="scroll", **kw)
    th = cfg.resolve_theme()
    words = read_textgrid(long_media["textgrid"]).words
    return build_scroll(words, th, cfg, resolve_font(None, th.font_candidates)), cfg, th


def test_all_words_in_order_exactly_once(long_media):
    sl, *_ = build(long_media)
    assert [w for l in sl.lines for w in l.words] == list(sl.words)
    assert [l.first for l in sl.lines] == [sum(len(x.words) for x in sl.lines[:i]) for i in range(len(sl.lines))]
    assert len(sl.lines) > 8  # many lines on one scrolling page


def test_lines_fit_box_horizontally(long_media):
    sl, cfg, th = build(long_media)
    mx = th.safe_margin_frac * cfg.width
    for l in sl.lines:
        x0, _, x1, _ = l.layout.ink_bbox
        assert x0 >= mx - 1 and x1 <= cfg.width - mx + 1


def test_scroll_follows_mfa_line_start_times(long_media):
    sl, cfg, _ = build(long_media)
    d, ease = cfg.scroll.duration, cfg.scroll.easing
    assert sl.offset_at(0.0, d, ease) == 0.0
    for k in range(1, len(sl.lines)):
        trig = sl.triggers[k]
        assert trig == sl.lines[k].words[0].start
        assert sl.offset_at(trig - 1e-4, d, ease) <= sl.lines[k - 1].y + 1e-6  # not moving before the word starts
        done = min(trig + d, sl.triggers[k + 1] if k + 1 < len(sl.lines) else 1e9)
        assert sl.offset_at(done + 1e-4 if k + 1 == len(sl.lines) else done, d, ease) == pytest.approx(sl.lines[k].y, abs=1e-6)
    ts = [i * 0.01 for i in range(int(sl.triggers[-1] * 100) + 80)]
    offs = [sl.offset_at(t, d, ease) for t in ts]
    assert all(b >= a - 1e-9 for a, b in zip(offs, offs[1:]))  # never scrolls backwards


def test_break_on_sentence(long_media):
    from storyframe.validation import apply_transcript
    cfg = RenderConfig(width=1920, height=1080, grouping="scroll", scroll={"break_on_sentence": True})
    th = cfg.resolve_theme()
    words = apply_transcript(read_textgrid(long_media["textgrid"]).words, mf.LONG_TRANSCRIPT)
    sl = build_scroll(words, th, cfg, resolve_font(None, th.font_candidates))
    for l in sl.lines[:-1]:
        # a sentence end may only appear as a line's last word
        assert not any(w.text.endswith(".") for w in l.words[:-1])
    assert any(l.words[-1].text == "moon." for l in sl.lines)


def test_overlong_word_is_error(long_media):
    cfg = RenderConfig(width=1920, height=1080, grouping="scroll", min_font_size=60, font_size=100)
    th = cfg.resolve_theme()
    with pytest.raises(LayoutError):
        build_scroll([Word("x" * 80, 0, 1)], th, cfg, resolve_font(None, th.font_candidates))


def test_scroll_config_validation():
    with pytest.raises(ConfigError):
        RenderConfig(scroll={"window_height": 5}).validate()
    assert RenderConfig.from_dict({"grouping": "scroll", "scroll": {"duration": 0.3}}).scroll.duration == 0.3
