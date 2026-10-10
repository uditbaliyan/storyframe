"""Generate a synthetic narration (tone bursts) plus an MFA-style TextGrid (words + phones tiers).

The TextGrid mimics MFA's long-format output: lowercase punctuation-free word labels, empty intervals
for pauses, and a phones tier. It is synthetic: it was NOT produced by MFA.
"""
from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

TRANSCRIPT = "Once upon a time, there was a little fox who dreamed of the moon. Every night, he climbed the tallest hill and waited."


def build_timing(transcript: str = TRANSCRIPT, lead: float = 0.35):
    """Return ([(label, start, end)], total_duration). Pauses follow commas/periods."""
    t = lead
    items = []
    for tok in transcript.split():
        label = "".join(c for c in tok.lower() if c.isalnum() or c == "'")
        dur = 0.14 + 0.055 * len(label)
        items.append((label, round(t, 3), round(t + dur, 3)))
        t += dur + 0.03
        if tok.endswith(","):
            t += 0.25
        elif tok.endswith("."):
            t += 0.6
    return items, round(t + 0.3, 3)


def textgrid_text(items, total, word_tier="words", phone_tier="phones", short=False) -> str:
    def fill(ivs, xmax):
        out, cur = [], 0.0
        for lab, s, e in ivs:
            if s > cur + 1e-9:
                out.append(("", cur, s))
            out.append((lab, s, e))
            cur = e
        if cur < xmax - 1e-9:
            out.append(("", cur, xmax))
        return out

    words = fill(items, total)
    phones = []
    for lab, s, e in items:
        n = 3 if len(lab) >= 3 else 1
        step = (e - s) / n
        for k in range(n):
            phones.append((f"P{k}", round(s + k * step, 4), round(s + (k + 1) * step, 4) if k < n - 1 else e))
    phones = fill(phones, total)
    tiers = [(word_tier, words), (phone_tier, phones)]
    if short:
        lines = ['File type = "ooTextFile"', 'Object class = "TextGrid"', "", "0", f"{total}", "<exists>", str(len(tiers))]
        for name, ivs in tiers:
            lines += ['"IntervalTier"', f'"{name}"', "0", f"{total}", str(len(ivs))]
            for lab, s, e in ivs:
                lines += [str(s), str(e), f'"{lab}"']
        return "\n".join(lines) + "\n"
    lines = ['File type = "ooTextFile"', 'Object class = "TextGrid"', "", "xmin = 0 ", f"xmax = {total} ", "tiers? <exists> ", f"size = {len(tiers)} ", "item []: "]
    for ti, (name, ivs) in enumerate(tiers, 1):
        lines += [f"    item [{ti}]:", '        class = "IntervalTier" ', f'        name = "{name}" ', "        xmin = 0 ", f"        xmax = {total} ", f"        intervals: size = {len(ivs)} "]
        for k, (lab, s, e) in enumerate(ivs, 1):
            lines += [f"        intervals [{k}]:", f"            xmin = {s} ", f"            xmax = {e} ", f'            text = "{lab}" ']
    return "\n".join(lines) + "\n"


def write_wav(path: Path, items, total: float, sr: int = 24000) -> None:
    n = int(total * sr)
    t = np.arange(n) / sr
    sig = np.zeros(n, np.float32)
    for k, (_, s, e) in enumerate(items):
        a, b = int(s * sr), int(e * sr)
        f = 180 + 25 * (k % 7)
        env = np.hanning(b - a)
        sig[a:b] += 0.35 * np.sin(2 * np.pi * f * t[a:b]) * env
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((sig * 32767).astype(np.int16).tobytes())


LONG_TRANSCRIPT = (
    "Once upon a time, there was a little fox who dreamed of the moon. Every night, he climbed the tallest hill and waited. "
    "The other animals laughed at him, but he never gave up. One evening, a tiny star fell from the sky and landed beside him. "
    "It was warm, and it glowed like a small lantern. The fox picked it up gently and whispered, thank you. "
    "From that night on, the forest was never dark again, and the little fox was never alone."
)


def write_all(directory: Path, name: str = "sample", transcript: str = TRANSCRIPT, **kw) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    items, total = build_timing(transcript, **kw)
    paths = {"textgrid": directory / f"{name}.TextGrid", "audio": directory / f"{name}.wav", "transcript": directory / f"{name}.txt"}
    paths["textgrid"].write_text(textgrid_text(items, total), encoding="utf-8")
    paths["transcript"].write_text(transcript, encoding="utf-8")
    write_wav(paths["audio"], items, total)
    return paths


if __name__ == "__main__":
    print(write_all(Path(__file__).parent))
