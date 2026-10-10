import pytest

from storyframe.config import RenderConfig
from storyframe.exceptions import ConfigError, LayoutError, ThemeNotFoundError
from storyframe.grouping import group_words, resolve_params
from storyframe.layout import LayoutEngine
from storyframe.models import CaptionGroup, Word
from storyframe.themes import get_theme, list_themes
from storyframe.typography import resolve_font
from storyframe.exceptions import FontNotFoundError


def engine(theme="english_pink_story", **kw):
    cfg = RenderConfig(theme=theme, **kw)
    th = cfg.resolve_theme()
    return LayoutEngine(th, cfg, resolve_font(cfg.font, th.font_candidates)), cfg, th


def G(*texts):
    return CaptionGroup(tuple(Word(t, i * 0.4, i * 0.4 + 0.35) for i, t in enumerate(texts)))


@pytest.mark.parametrize("theme", [t.name for t in list_themes()])
@pytest.mark.parametrize("mode", ["phrase", "sentence", "short_form", "word"])
def test_nothing_clips_in_any_theme_or_mode(words, theme, mode):
    eng, cfg, th = engine(theme)
    pairs = eng.fit_groups(group_words(words, resolve_params(mode)))
    mx, my = th.safe_margin_frac * cfg.width, th.safe_margin_frac * cfg.height
    for g, lay in pairs:
        x0, y0, x1, y1 = lay.ink_bbox
        assert x0 >= mx - 1 and x1 <= cfg.width - mx + 1, g.text
        assert y0 >= my - 1 and y1 <= cfg.height - my + 1, g.text
        assert eng.min_size <= lay.font_size <= eng.preferred
        assert len(lay.lines) <= eng.max_lines


def test_lines_are_whole_words_and_balanced():
    eng, *_ = engine()
    lay = eng.layout_group(G("Once", "upon", "a", "time,", "there"))
    assert sorted(i for l in lay.lines for i in l) == [0, 1, 2, 3, 4]
    widths = [sum(lay.word_widths[i] for i in l) for l in lay.lines]
    assert len(lay.lines) > 1 and max(widths) / min(widths) < 2.2


def test_font_shrinks_only_when_needed():
    eng, *_ = engine()
    assert eng.layout_group(G("Hi", "there")).font_size == eng.preferred
    assert eng.layout_group(G("extraordinarily", "uncharacteristically")).font_size < eng.preferred


def test_min_font_size_enforced_and_long_word_never_clipped():
    eng, *_ = engine(min_font_size=40)
    with pytest.raises(LayoutError):
        eng.layout_group(G("Pneumonoultramicroscopicsilicovolcanoconiosis" * 2))
    with pytest.raises(LayoutError, match="too wide"):
        eng.fit_groups([G("Pneumonoultramicroscopicsilicovolcanoconiosis" * 2)])


def test_unfittable_group_is_split_not_clipped():
    eng, *_ = engine(font_size=150, min_font_size=140)
    notes = []
    pairs = eng.fit_groups([G(*"the quick brown fox jumps over the lazy dog today".split())], notes)
    assert len(pairs) > 1 and notes
    assert [w.text for g, _ in pairs for w in g.words] == "the quick brown fox jumps over the lazy dog today".split()


def test_user_font_size_override():
    eng, *_ = engine(font_size=100)
    assert eng.preferred == 100


def test_centered_horizontally():
    eng, cfg, _ = engine()
    x0, _, x1, _ = eng.layout_group(G("Hello", "world")).ink_bbox
    assert abs((x0 + x1) / 2 - cfg.width / 2) < 3


def test_missing_font_is_error():
    with pytest.raises(FontNotFoundError):
        resolve_font("/no/such/font.ttf", ())
    with pytest.raises(FontNotFoundError):
        resolve_font(None, ("DefinitelyNotAFont-Bold",)) if False else resolve_font("DefinitelyNotAFont", ())


def test_theme_and_config_validation():
    with pytest.raises(ThemeNotFoundError):
        get_theme("nope")
    for bad in (dict(width=1081), dict(fps=0), dict(grouping="x"), dict(crf=99)):
        with pytest.raises(ConfigError):
            RenderConfig(**bad).validate()
    with pytest.raises(ConfigError):
        RenderConfig.from_dict({"bogus": 1})
    cfg = RenderConfig.from_dict({"grouping": "phrase", "animation": {"entrance": "pop"}, "theme_overrides": {"accent": [1, 2, 3]}})
    assert cfg.resolve_theme().accent == (1, 2, 3)
