# Themes and customization

`storyframe themes` lists built-ins: `english_pink_story` (default), `cinematic_dark`, `minimal_subtitles`.

`english_pink_story`: pastel pink gradient with soft light, vignette, faint deterministic grain and +-1.2% brightness breathing; black fill, white outline (11.5% of font size), blurred dark edge/shadow, coral accent for the active word; font 14% of frame width.

## Overrides
```python
RenderConfig(theme="english_pink_story",
             theme_overrides={"accent": (255, 190, 40), "outline_frac": 0.09, "max_lines": 2},
             font="/path/Font-Bold.ttf", font_size=140, min_font_size=80,
             background={"style": "solid", "texture": False, "animate": False},   # or {"image": "bg.jpg"}
             animation={"entrance": "pop", "entrance_duration": 0.18, "easing": "ease_out_cubic", "reduced_motion": False})
```
Theme fields: font candidates, size fractions, `fill/accent/outline`, outline/shadow geometry, `line_spacing`, `align`, `valign`, text-box width/height/centre, `safe_margin_frac`, `max_lines`, `default_entrance`, and a `BackgroundSpec`. Register your own with `storyframe.themes.register_theme(Theme(...))`.

## Animations (`animation.entrance`)
`fade`, `slide_up`, `pop` (scale-in, never overshoots the layout box), `word_reveal` (words appear at their MFA start; layout is fixed so nothing reflows), `none` (static, hard cuts). `reduced_motion=True` forces fades only. Durations are shortened automatically for very short groups. Highlight state depends only on time and MFA intervals, never on animation.

## Fonts
Explicit `--font` must exist (file path or installed name) or rendering stops. Without it, the theme's candidate list is searched in standard font directories, then `fc-match`. Use a bold/heavy font file for a bold look; faux-bold is not synthesized.

## Scroll mode (`grouping="scroll"`)
All words are flowed into lines at one fixed font size (`font_scale` x the theme size, or `font_size` if set). The active word follows MFA intervals as usual. The page stays put until the first word of the next line starts, then glides up over `scroll.duration` (shortened if the next line starts sooner). Lines fade out near the top and bottom of the window instead of being cut. Fixed position means no re-wrapping, so highlight and scroll cannot drift apart. Static captions during pauses are replaced by a continuous page that fades in before the first word and out after the last.
