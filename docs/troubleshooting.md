# Troubleshooting

| Symptom / message | Fix |
|---|---|
| `'ffmpeg' not found on PATH` | Install FFmpeg, run `storyframe doctor`. |
| `ambiguous word tier` / `cannot identify the word tier` | Pass `--word-tier "<name>"`; names are listed in the error. |
| `last word ends at ...s but the audio is only ...` | Wrong audio, or TextGrid from a trimmed clip: use `--time-offset`. |
| `transcript does not match` | Fix the transcript or re-align; differences are listed with times. Nothing is shifted automatically. |
| `already exists` | `--overwrite`. |
| `does not fit in N line(s)` / `too wide` | Lower `min_font_size`, raise theme `max_lines`, use a narrower font, or use `word` grouping. |
| Font looks thin or generic | Pass `--font /path/to/ExtraBold.ttf`. |
| Output colours differ slightly in a player | Output is tagged BT.709 limited range; update the player or re-encode. |
| Slow render | Lower `--fps`, `--width/--height`, or use `preset="veryfast"` in config. |
| `ffmpeg exited with status ...` | The FFmpeg stderr tail is included in the message; check codec/preset support with `storyframe doctor`. |
