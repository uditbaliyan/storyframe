"""StoryFrame: render word-synchronized English storytelling videos from audio + MFA TextGrid."""
from .api import render_preview, render_video, validate_inputs
from .config import AnimationConfig, BackgroundConfig, GroupingOptions, RenderConfig
from .exceptions import StoryFrameError
from .models import CaptionGroup, RenderResult, ValidationReport, Word

__version__ = "0.1.0"
__all__ = [
    "render_video", "render_preview", "validate_inputs", "RenderConfig", "GroupingOptions", "AnimationConfig",
    "BackgroundConfig", "RenderResult", "ValidationReport", "Word", "CaptionGroup", "StoryFrameError", "__version__",
]
