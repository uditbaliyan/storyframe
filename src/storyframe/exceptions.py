"""Exception hierarchy. Every error raised deliberately by StoryFrame derives from StoryFrameError."""
from __future__ import annotations


class StoryFrameError(Exception):
    """Base class for all StoryFrame errors."""


class ConfigError(StoryFrameError):
    """Invalid configuration value."""


class InputFileError(StoryFrameError):
    """An input file is missing, unreadable, or empty."""


class TextGridError(StoryFrameError):
    """The TextGrid is malformed or cannot be parsed."""


class WordTierError(TextGridError):
    """The word tier is missing or cannot be identified unambiguously."""


class TimingError(StoryFrameError):
    """Invalid, overlapping, or out-of-order timestamps."""


class DurationMismatchError(TimingError):
    """Alignment and audio durations are incompatible."""


class TranscriptMismatchError(StoryFrameError):
    """Transcript tokens do not match the timed word sequence."""

    def __init__(self, message: str, mismatches: list[str] | None = None):
        super().__init__(message)
        self.mismatches = mismatches or []


class ThemeNotFoundError(ConfigError):
    """Unknown theme name."""


class FontNotFoundError(StoryFrameError):
    """Requested or default font could not be located."""


class LayoutError(StoryFrameError):
    """A caption cannot be laid out inside the configured bounds."""


class FFmpegNotFoundError(StoryFrameError):
    """ffmpeg/ffprobe is not installed or not on PATH."""


class MediaProbeError(StoryFrameError):
    """ffprobe could not read the media file."""


class RenderError(StoryFrameError):
    """The encoder failed or was interrupted."""


class OutputExistsError(StoryFrameError):
    """The output file exists and overwrite was not requested."""


class OutputVerificationError(StoryFrameError):
    """The rendered file failed post-render verification."""
