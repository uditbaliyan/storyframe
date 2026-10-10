# Preparing MFA input

StoryFrame reads a Praat TextGrid. MFA writes (long format) one interval tier for words and one for phones; with multiple speakers, tiers are named `<speaker> - words` / `<speaker> - phones`.

> The bundled fixtures are *synthetic imitations* of this layout. They were not produced by an MFA run. Run `storyframe validate` on your real output first.

## Word tier selection
1. `--word-tier NAME` (exact, then case-insensitive match) wins.
2. Otherwise exactly one interval tier named `words`/`word` (or ending in ` - words`) is used.
3. Several candidates (multi-speaker) -> error asking for `--word-tier`.
4. No candidate -> error listing all tiers. A lone non-phone interval tier is used with a warning.
Phone tiers are never rendered.

## Silence, empty intervals, labels
Skipped: empty text, `sil`, `sp`, `silence`, `<eps>`, `<sil>`, `{sil}`, `<p:>`, `#` (case-insensitive). Override with `RenderConfig(silence_labels=(...))`. Any other label is treated as a spoken word and kept, including `<unk>` (warned; supply a transcript so the real word is shown). Punctuation present in labels is preserved.
Invalid structure (overlap, out-of-order, end<start, intervals outside the grid) stops with the offending times.

## Matching audio and alignment
`validate` checks that the last word fits inside the audio and that TextGrid duration is within `duration_tolerance` (default 0.35 s) of the audio duration. If the TextGrid came from a trimmed clip of a longer recording, pass `--time-offset SECONDS`, which is added to every TextGrid time; StoryFrame never guesses an offset. `strict_duration=False` downgrades a mismatch to a warning.

## Optional transcript
MFA labels are usually lowercase and punctuation-free. `--transcript script.txt` supplies display text. Tokens are split on whitespace and compared after lowercasing and stripping punctuation. Equal sequences -> display text replaced, timestamps untouched. Any difference -> `TranscriptMismatchError` listing each difference with its time (e.g. `near 3.40s [TextGrid only]: 'little'`).
Common causes: a numeral vs spelled-out word, a hyphenated word MFA split into two, text edited after alignment, a dash with no spaces (`word—word`).
