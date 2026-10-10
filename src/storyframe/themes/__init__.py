"""Built-in themes. Importing this package registers them."""
from . import cinematic_dark, english_pink_story, minimal_subtitles
from .registry import BackgroundSpec, Theme, get_theme, list_themes, register_theme

for _m in (english_pink_story, cinematic_dark, minimal_subtitles):
    register_theme(_m.THEME, replace=True)

__all__ = ["Theme", "BackgroundSpec", "get_theme", "list_themes", "register_theme"]
