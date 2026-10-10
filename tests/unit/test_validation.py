import pytest

from storyframe.exceptions import DurationMismatchError, TimingError, TranscriptMismatchError
from storyframe.models import Word
from storyframe.timeline import apply_offset
from storyframe.validation import apply_transcript, check_duration, normalize_token, tokenize_transcript
import make_fixtures as mf


def W(t, s, e):
    return Word(t, s, e, original_text=t)


def test_duration_ok_within_tolerance():
    check_duration([W("a", 0, 1.0)], 1.2, 0.0, 1.25, 0.35, True, [])


def test_audio_shorter_than_alignment_fails():
    with pytest.raises(DurationMismatchError, match="only"):
        check_duration([W("a", 0, 10.0)], 10.0, 0.0, 6.0, 0.35, True, [])


def test_duration_mismatch_is_warning_when_not_strict():
    w = []
    check_duration([W("a", 0, 5.0)], 5.0, 0.0, 9.0, 0.35, False, w)
    assert w and "differs" in w[0]


def test_offset_shifts_without_changing_durations():
    ws = [W("a", 1.0, 1.5), W("b", 1.6, 2.0)]
    out = apply_offset(ws, 2.5)
    assert [(w.start, w.end) for w in out] == [(3.5, 4.0), (4.1, 4.5)]
    assert out[0].duration == pytest.approx(0.5)


def test_offset_before_zero_rejected():
    with pytest.raises(TimingError):
        apply_offset([W("a", 1.0, 1.5)], -2.0)


def test_offset_fixes_duration_check():
    check_duration([W("a", 6.0, 8.0)], 8.0, 0.0, 8.0, 0.35, True, [])
    check_duration([W("a", 6.0 + 4, 8.0 + 4)], 8.0 + 4, 0.0, 12.0, 0.35, True, [])


def test_normalization():
    assert normalize_token("Don’t,") == "don't"
    assert normalize_token("\"Hello!\"") == "hello"
    assert tokenize_transcript("Wait — what?") == ["Wait—", "what?"]


def test_transcript_restores_text_and_keeps_times(words):
    out = apply_transcript(words, mf.TRANSCRIPT)
    assert out[0].text == "Once" and out[3].text == "time," and out[13].text == "moon."
    assert [(w.start, w.end) for w in out] == [(w.start, w.end) for w in words]
    assert out[0].original_text == "once"


def test_transcript_mismatch_reports_instead_of_shifting(words):
    bad = mf.TRANSCRIPT.replace("little ", "")
    with pytest.raises(TranscriptMismatchError) as e:
        apply_transcript(words, bad)
    assert "NOT shifted" in str(e.value) and "little" in str(e.value)


def test_transcript_extra_and_changed_words(words):
    with pytest.raises(TranscriptMismatchError):
        apply_transcript(words, mf.TRANSCRIPT + " Goodbye.")
    with pytest.raises(TranscriptMismatchError):
        apply_transcript(words, mf.TRANSCRIPT.replace("fox", "wolf"))
