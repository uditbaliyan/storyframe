import pytest

from storyframe.config import GroupingOptions
from storyframe.grouping import ends_strong, group_words, resolve_params
from storyframe.models import Word
from storyframe.timeline import active_word_index, revealed_count, schedule_groups


def test_groups_cover_all_words_in_order_with_exact_times(words):
    for mode in ("phrase", "sentence", "short_form", "word"):
        groups = group_words(words, resolve_params(mode))
        flat = [w for g in groups for w in g.words]
        assert flat == words  # same objects/timestamps, same order, nothing dropped
        for g in groups:
            assert g.start == g.words[0].start and g.end == g.words[-1].end


def test_short_form_limits(words):
    p = resolve_params("short_form")
    for g in group_words(words, p):
        assert len(g.words) <= p.max_words
        assert len(g.text) <= p.max_chars


def test_word_mode_is_one_word_per_group(words):
    assert all(len(g.words) == 1 for g in group_words(words, resolve_params("word")))


def test_sentence_mode_breaks_at_sentence_ends(words_tr):
    groups = group_words(words_tr, resolve_params("sentence"))
    assert len(groups) == 2
    assert groups[0].words[-1].text == "moon."


def test_phrase_mode_splits_long_sentence_balanced(words):
    groups = group_words(words, resolve_params("phrase"))
    sizes = [len(g.words) for g in groups]
    assert max(sizes) <= 7 and min(sizes) >= 2


def test_no_orphan_single_words_in_default_mode(words):
    assert all(len(g.words) >= 2 for g in group_words(words, resolve_params("short_form")))


def test_gap_forces_boundary():
    ws = [Word("a", 0, 0.3), Word("b", 0.35, 0.6), Word("c", 2.0, 2.3), Word("d", 2.35, 2.6)]
    groups = group_words(ws, resolve_params("sentence"))
    assert [len(g.words) for g in groups] == [2, 2]


def test_punctuation_toggle():
    ws = [Word("Hi.", 0, 0.3), Word("There", 0.35, 0.6)]
    assert len(group_words(ws, resolve_params("sentence"))) == 2
    off = resolve_params("sentence", GroupingOptions(break_on_punctuation=False))
    assert len(group_words(ws, off)) == 1


def test_split_long_sentences_off_keeps_sentence_whole(words_tr):
    p = resolve_params("short_form", GroupingOptions(split_long_sentences=False))
    assert len(group_words(words_tr, p)) == 2


def test_abbreviation_not_sentence_end():
    assert ends_strong("end.") and ends_strong("Really?\"") and not ends_strong("Mr.")


def test_max_duration_respected():
    ws = [Word(f"w{i}", i * 1.0, i * 1.0 + 0.9) for i in range(8)]
    p = resolve_params("phrase", GroupingOptions(max_words=8, max_duration=3.0, max_gap=5))
    assert all(g.duration <= 3.0 for g in group_words(ws, p))


def test_active_word_follows_intervals_not_group_duration():
    ws = [Word("a", 1.0, 1.1), Word("b", 1.1, 3.0), Word("c", 3.5, 3.6)]
    g = group_words(ws, resolve_params("sentence", GroupingOptions(max_gap=5)))[0]
    assert active_word_index(g, 1.05) == 0
    assert active_word_index(g, 1.1) == 1
    assert active_word_index(g, 2.9) == 1  # long word stays active for its whole MFA interval
    assert active_word_index(g, 3.2) == -1  # gap: nothing invented
    assert active_word_index(g, 3.55) == 2
    assert revealed_count(g, 0.9) == 0 and revealed_count(g, 3.55) == 3


def test_schedule_never_shows_stale_text_across_gap():
    ws = [Word("a", 0, 0.5), Word("b", 5.0, 5.5)]
    groups = schedule_groups(group_words(ws, resolve_params("word")), linger=0.12, exit_duration=0.1)
    assert groups[0].visible_end == pytest.approx(0.72)
    ws2 = [Word("a", 0, 0.5), Word("b", 0.52, 1.0)]
    g2 = schedule_groups(group_words(ws2, resolve_params("word")), 0.12, 0.1)
    assert g2[0].visible_end == pytest.approx(0.52)  # capped at next start
