import pytest

import make_fixtures as mf
from storyframe.adapters.mfa_textgrid import read_textgrid
from storyframe.exceptions import StoryFrameError, TextGridError, TimingError, WordTierError


def test_long_format_words_only(media, items):
    al = read_textgrid(media["textgrid"])
    assert al.tier_name == "words"
    assert al.tier_names == ["words", "phones"]
    assert len(al.words) == len(items[0]) == 23
    assert [w.text for w in al.words][:4] == ["once", "upon", "a", "time"]
    assert al.words[0].start == pytest.approx(0.35)
    assert al.xmax == pytest.approx(items[1])


def test_short_format(make_tg, items):
    p = make_tg(*items, short=True)
    al = read_textgrid(p)
    assert len(al.words) == 23 and al.words[0].text == "once"


def test_order_preserved_and_phone_tier_ignored(media):
    al = read_textgrid(media["textgrid"])
    starts = [w.start for w in al.words]
    assert starts == sorted(starts)
    assert not any(w.text.startswith("P") and w.text[1:].isdigit() for w in al.words)


def test_speaker_prefixed_tier_detected(make_tg, items):
    p = make_tg(*items, word_tier="spk1 - words", phone_tier="spk1 - phones")
    assert read_textgrid(p).tier_name == "spk1 - words"


def test_explicit_tier_override_resolves_ambiguity(make_tg, items):
    p = make_tg(*items, word_tier="spk1 - words", phone_tier="spk2 - words")
    with pytest.raises(WordTierError, match="ambiguous"):
        read_textgrid(p)
    assert read_textgrid(p, word_tier="spk2 - words").tier_name == "spk2 - words"
    assert read_textgrid(p, word_tier="SPK1 - WORDS").tier_name == "spk1 - words"


def test_missing_word_tier_actionable(make_tg, items):
    p = make_tg(*items, word_tier="phones", phone_tier="phones2")
    with pytest.raises(WordTierError, match="--word-tier"):
        read_textgrid(p)


def test_unknown_explicit_tier(media):
    with pytest.raises(WordTierError, match="not found"):
        read_textgrid(media["textgrid"], word_tier="nope")


def test_malformed_textgrid(tmp_path):
    p = tmp_path / "bad.TextGrid"
    p.write_text("this is not a textgrid\n")
    with pytest.raises(TextGridError):
        read_textgrid(p)


def test_empty_intervals_and_default_silence_skipped(make_tg):
    items = [("sil", 0.0, 0.3), ("hello", 0.3, 0.8), ("sp", 0.8, 1.0), ("world", 1.0, 1.5)]
    al = read_textgrid(make_tg(items, 1.6))
    assert [w.text for w in al.words] == ["hello", "world"]


def test_custom_silence_labels_and_unknown_labels_kept(make_tg):
    items = [("hello", 0.0, 0.5), ("xyz", 0.5, 0.9), ("world", 0.9, 1.4)]
    p = make_tg(items, 1.5)
    assert [w.text for w in read_textgrid(p).words] == ["hello", "xyz", "world"]  # unfamiliar != silence
    assert [w.text for w in read_textgrid(p, silence_labels=["xyz", ""]).words] == ["hello", "world"]


def test_unk_label_warns(make_tg):
    al = read_textgrid(make_tg([("hello", 0.0, 0.5), ("<unk>", 0.5, 0.9)], 1.0))
    assert any("<unk>" in w for w in al.warnings)


def test_zero_length_interval_rejected_with_diagnostic(make_tg):
    with pytest.raises(TextGridError, match="cannot occur after"):
        read_textgrid(make_tg([("a", 0.1, 0.5), ("b", 0.6, 0.6), ("c", 0.7, 1.0)], 1.1))


@pytest.mark.parametrize("bad", [[("a", 0.5, 1.0), ("b", 0.8, 1.2)], [("a", 1.0, 1.5), ("b", 0.2, 0.5)]])
def test_overlapping_or_out_of_order_rejected(make_tg, bad):
    with pytest.raises((TimingError, TextGridError)):
        read_textgrid(make_tg(bad, 2.0))


def test_only_silence_is_an_error(make_tg):
    with pytest.raises(WordTierError, match="no spoken words"):
        read_textgrid(make_tg([("sil", 0.0, 1.0)], 1.0))


def test_all_errors_share_base(tmp_path):
    p = tmp_path / "bad.TextGrid"
    p.write_text("x")
    with pytest.raises(StoryFrameError):
        read_textgrid(p)
