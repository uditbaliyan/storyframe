# Architecture decision record

## Decision
Primary renderer: **Pillow (text sprites) + numpy compositing, raw RGB frames piped into FFmpeg (libx264 + AAC)**. Internal interface: `Renderer.render(RenderPlan, output)`; the plan holds groups, layouts, theme and audio info, never TextGrid objects.

## Options compared
| | A: FFmpeg + ASS/libass | B: Pillow + FFmpeg pipe (chosen) | C: Browser/SVG/Canvas |
|---|---|---|---|
| Word timing/highlight | `\k` karaoke tags work, but highlight shape is a wipe/fill, not clean per-word state | Exact: state chosen from MFA intervals per frame | Exact (JS) |
| Outline + shadow | libass border/shadow OK; outline is pixel-ring, limited blur control | Full control (stroke, blurred shadow layer, two-pass fill so strokes never cover neighbors) | Excellent (CSS/SVG) |
| Layout | libass wraps by its own rules; balanced lines and fit-to-box need pre-measurement anyway | Own measured, balanced layout; same engine reused by every theme | Good, but needs a browser to measure |
| Animation | `\t`/`\fad` fine for fade/move; scale-in awkward | Any transform per frame | Best |
| Speed | Fastest | ~2x realtime at 1080x1920 (cached sprites, one blend per frame) | Slowest (frame capture) |
| Install | Needs FFmpeg built with libass + fontconfig | FFmpeg + pure-Python wheels | Chromium/Playwright (~150 MB+) |
| Testability | Visual checks need full render | Frame function is pure: `frame_at(t)` unit-testable without FFmpeg | Needs browser in CI |

A cannot give layout-correct, layout-measured captions without a measurement step that B already does. C adds a browser runtime without a visual benefit this theme needs. B was chosen as the simplest renderer that satisfies sync, typography and testability.

## Measured
Benchmark on the 11.3 s fixture, 1080x1920@30 (340 frames), 1 CPU core: 23 s end-to-end including libx264 `medium` and verification. Memory: one frame plus cached sprites for the current group only; no frames stored on disk.

## Key design points
- **Time**: seconds throughout; frames sampled at the display-interval midpoint `(n+0.5)/fps`, so highlight onset error is within +-1/2 frame.
- **Sprites**: one RGBA sprite per (group, active word, revealed count); entrance/exit only change alpha/offset/scale of that sprite, so animation cannot move the highlight.
- **Colour**: RGB->YUV via BT.709 limited range with matching container tags.
- **Atomic output**: encode to a hidden temp file in the output directory, verify (streams, size, fps, duration, full decode), then `os.replace`. Interrupt/failure removes the temp file.
- **Adapter boundary**: `adapters/mfa_textgrid.py` is the only code that knows TextGrids (uses `praatio`; chosen over a hand-written Praat parser because it handles long/short formats and encodings).
