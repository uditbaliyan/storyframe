import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "fixtures"))
import make_fixtures as mf  # noqa: E402

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def pytest_collection_modifyitems(config, items):
    if HAVE_FFMPEG:
        return
    skip = pytest.mark.skip(reason="ffmpeg/ffprobe not installed; media integration tests skipped")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def items():
    return mf.build_timing()


@pytest.fixture
def media(tmp_path):
    """Synthetic wav + MFA-style long-format TextGrid + transcript in tmp_path (needs no ffmpeg)."""
    return mf.write_all(tmp_path)


@pytest.fixture
def make_tg(tmp_path):
    def _make(items, total, name="x.TextGrid", **kw):
        p = tmp_path / name
        p.write_text(mf.textgrid_text(items, total, **kw), encoding="utf-8")
        return p
    return _make


@pytest.fixture
def words(media):
    from storyframe.adapters.mfa_textgrid import read_textgrid
    return read_textgrid(media["textgrid"]).words


def running_as_root():
    return hasattr(os, "geteuid") and os.geteuid() == 0


@pytest.fixture
def words_tr(media, words):
    from storyframe.validation import apply_transcript
    return apply_transcript(words, media["transcript"].read_text())


@pytest.fixture
def long_media(tmp_path):
    d = tmp_path / "long"
    return mf.write_all(d, transcript=mf.LONG_TRANSCRIPT)
