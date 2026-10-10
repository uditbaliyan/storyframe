"""Layout engine: measures real text, balances lines, picks the largest font size that fits, never clips."""
from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from .config import RenderConfig
from .exceptions import LayoutError
from .animations import EASINGS
from .grouping import ends_strong, split_group
from .models import CaptionGroup, Word
from .themes import Theme
from .typography import FontMeasurer

_SIZE_STEP = 2


@dataclass(frozen=True)
class CaptionLayout:
    font_size: int
    lines: tuple[tuple[int, ...], ...]
    positions: tuple[tuple[float, float], ...]  # per word: (x, baseline_y) in block coords (origin = block top-left)
    word_widths: tuple[float, ...]
    block_w: float
    block_h: float
    stroke: int
    shadow_extra: int
    shadow_offset: tuple[float, float]
    shadow_blur: float
    pad: int
    sprite_w: int
    sprite_h: int
    origin: tuple[int, int]  # sprite top-left in frame coords
    ascent: float
    descent: float

    def word_box(self, i: int) -> tuple[float, float, float, float]:
        """Frame-coordinate box (x0, y0, x1, y1) of word i's glyph ink including outline."""
        x, y = self.positions[i]
        ox = self.origin[0] + self.pad
        oy = self.origin[1] + self.pad
        return (ox + x - self.stroke, oy + y - self.ascent - self.stroke, ox + x + self.word_widths[i] + self.stroke, oy + y + self.descent + self.stroke)

    @property
    def ink_bbox(self) -> tuple[float, float, float, float]:
        boxes = [self.word_box(i) for i in range(len(self.positions))]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _balanced(widths: list[float], space: float, n_lines: int, max_w: float) -> list[tuple[int, int]] | None:
    """Partition words into exactly n_lines contiguous lines minimising squared deviation from the mean width."""
    m = len(widths)
    if n_lines > m:
        return None
    pre = [0.0]
    for w in widths:
        pre.append(pre[-1] + w)

    def lw(i, j):  # words i..j-1
        return pre[j] - pre[i] + space * (j - i - 1)

    target = lw(0, m) / n_lines
    INF = float("inf")
    dp = [[INF] * (m + 1) for _ in range(n_lines + 1)]
    back = [[0] * (m + 1) for _ in range(n_lines + 1)]
    dp[0][0] = 0.0
    for l in range(1, n_lines + 1):
        for j in range(l, m + 1):
            for i in range(l - 1, j):
                w = lw(i, j)
                if w > max_w or dp[l - 1][i] == INF:
                    continue
                c = dp[l - 1][i] + (w - target) ** 2
                if c < dp[l][j]:
                    dp[l][j], back[l][j] = c, i
    if dp[n_lines][m] == INF:
        return None
    spans, j = [], m
    for l in range(n_lines, 0, -1):
        i = back[l][j]
        spans.append((i, j))
        j = i
    return spans[::-1]


def _greedy_lines(widths: list[float], space: float, max_w: float) -> int | None:
    lines, cur = 1, None
    for w in widths:
        if w > max_w:
            return None
        if cur is None:
            cur = w
        elif cur + space + w <= max_w:
            cur += space + w
        else:
            lines += 1
            cur = w
    return lines


class LayoutEngine:
    def __init__(self, theme: Theme, config: RenderConfig, font_path: Path, max_lines: int | None = None):
        self.theme, self.cfg = theme, config
        self.measurer = FontMeasurer(font_path)
        W, H = config.width, config.height
        short = min(W, H)  # font scales with the shorter side so portrait, square and 16:9 look consistent
        self.preferred = config.font_size or round(theme.font_size_frac * short)
        self.min_size = config.min_font_size or max(8, round(theme.min_font_size_frac * short))
        self.max_lines = max_lines or theme.max_lines
        safe_w = W * (1 - 2 * theme.safe_margin_frac)
        self.box_w = min(W * theme.box_width_frac, safe_w, 1.3 * H if W > H else safe_w)  # keep landscape lines readable
        self.box_h = min(H * theme.box_height_frac, H * (1 - 2 * theme.safe_margin_frac))
        self.box_cx = W / 2
        self.box_cy = H * theme.box_center_y_frac
        if self.min_size > self.preferred:
            raise LayoutError(f"min font size {self.min_size}px exceeds preferred size {self.preferred}px")

    def _try(self, group: CaptionGroup, size: int) -> CaptionLayout | None:
        th, m = self.theme, self.measurer
        stroke = max(1, round(size * th.outline_frac))
        extra = round(size * th.shadow_extra_frac)
        blur = size * th.shadow_blur_frac
        sdx, sdy = size * th.shadow_offset_frac[0], size * th.shadow_offset_frac[1]
        pad = int(math.ceil(stroke + extra + blur * 3 + max(abs(sdx), abs(sdy)) + 2))
        avail = self.box_w - 2 * stroke
        texts = [w.text for w in group.words]
        widths = [m.width(size, t) for t in texts]
        space = m.width(size, " ")
        n = _greedy_lines(widths, space, avail)
        if n is None or n > self.max_lines:
            return None
        spans = _balanced(widths, space, n, avail)
        if spans is None:
            return None
        asc, desc = m.ink_extent(size)
        pitch = size * th.line_spacing
        block_h = (n - 1) * pitch + asc + desc
        if block_h + 2 * stroke > self.box_h:
            return None
        line_w = [sum(widths[i:j]) + space * (j - i - 1) for i, j in spans]
        block_w = max(line_w)
        W, H = self.cfg.width, self.cfg.height
        if th.align == "left":
            bx = self.box_cx - self.box_w / 2 + stroke
        elif th.align == "right":
            bx = self.box_cx + self.box_w / 2 - stroke - block_w
        else:
            bx = self.box_cx - block_w / 2
        if th.valign == "top":
            by = self.box_cy - self.box_h / 2 + stroke
        elif th.valign == "bottom":
            by = self.box_cy + self.box_h / 2 - stroke - block_h
        else:
            by = self.box_cy - block_h / 2
        # keep the whole box inside the frame even for off-centre boxes
        by = min(max(by, th.safe_margin_frac * H + stroke), H * (1 - th.safe_margin_frac) - stroke - block_h)
        ox, oy = int(math.floor(bx)) - pad, int(math.floor(by)) - pad
        bx_f, by_f = bx - (ox + pad), by - (oy + pad)  # sprite-local block origin (fractional part kept)
        positions = [(0.0, 0.0)] * len(texts)
        lines = []
        for li, (i, j) in enumerate(spans):
            lw_ = line_w[li]
            x0 = bx_f + {"left": 0.0, "right": block_w - lw_}.get(th.align, (block_w - lw_) / 2)
            y = by_f + asc + li * pitch
            x = x0
            for k in range(i, j):
                positions[k] = (x, y)
                x += widths[k] + space
            lines.append(tuple(range(i, j)))
        sw = int(math.ceil(block_w + 2 * pad + 2))
        sh = int(math.ceil(block_h + 2 * pad + 2))
        lay = CaptionLayout(size, tuple(lines), tuple(positions), tuple(widths), block_w, block_h, stroke, extra, (sdx, sdy), blur, pad, sw, sh, (ox, oy), asc, desc)
        # final guarantee: nothing outside the frame / safe region
        x0, y0, x1, y1 = lay.ink_bbox
        mx, my = th.safe_margin_frac * W, th.safe_margin_frac * H
        if x0 < mx - 1 or x1 > W - mx + 1 or y0 < my - 1 or y1 > H - my + 1:
            return None
        return lay

    def layout_group(self, group: CaptionGroup) -> CaptionLayout:
        """Largest size in [min, preferred] that fits. Raises LayoutError if even the minimum does not."""
        size = self.preferred
        while size >= self.min_size:
            lay = self._try(group, size)
            if lay is not None:
                return lay
            size -= _SIZE_STEP
        lay = self._try(group, self.min_size)
        if lay is not None:
            return lay
        raise LayoutError(f"caption {group.text!r} does not fit in {self.max_lines} line(s) at >= {self.min_size}px")

    def fit_groups(self, groups: list[CaptionGroup], notes: list[str] | None = None) -> list[tuple[CaptionGroup, CaptionLayout]]:
        """Lay out every group; groups that cannot fit are split (never clipped, never re-timed)."""
        out: list[tuple[CaptionGroup, CaptionLayout]] = []
        stack = list(reversed(groups))
        while stack:
            g = stack.pop()
            try:
                out.append((g, self.layout_group(g)))
            except LayoutError:
                parts = split_group(g)
                if parts is None or self.cfg.long_word_policy == "error" and len(g.words) == 1:
                    raise LayoutError(
                        f"word {g.text!r} is too wide to fit the text box at the minimum font size ({self.min_size}px). "
                        f"Lower min_font_size, choose a narrower font, or fix the transcript."
                    ) from None
                if notes is not None:
                    notes.append(f"split caption {g.text!r} at {g.start:.2f}s because it did not fit")
                stack.extend([parts[1], parts[0]])
        return out


@dataclass(frozen=True)
class ScrollLine:
    words: tuple[Word, ...]
    first: int  # index of the line's first word in the global word list
    layout: CaptionLayout  # single-line layout; origin y is unused (position comes from scroll)
    y: float  # line centre relative to line 0's centre


@dataclass(frozen=True)
class ScrollLayout:
    lines: tuple[ScrollLine, ...]
    words: tuple[Word, ...]
    pitch: float
    font_size: int
    triggers: tuple[float, ...]  # MFA start time of each line's first word

    def offset_at(self, t: float, duration: float, easing: str) -> float:
        """Scroll offset in px. Each glide starts at the MFA start of the new line's first word."""
        k = bisect_right(self.triggers, t) - 1
        if k <= 0:
            return 0.0
        nxt = self.triggers[k + 1] if k + 1 < len(self.triggers) else float("inf")
        d = min(duration, nxt - self.triggers[k])
        cur, prev = self.lines[k].y, self.lines[k - 1].y
        if d <= 0:
            return cur
        p = min(max((t - self.triggers[k]) / d, 0.0), 1.0)
        return cur - (1 - EASINGS[easing](p)) * (cur - prev)


def build_scroll(words: list[Word], theme: Theme, config: RenderConfig, font_path: Path) -> ScrollLayout:
    """Flow every word into lines at one fixed font size. Whole words only; nothing is clipped."""
    sc = config.scroll
    eng = LayoutEngine(theme, config, font_path)  # reuse box geometry
    short = min(config.width, config.height)
    size = config.font_size or round(theme.font_size_frac * short * sc.font_scale)
    min_size = config.min_font_size or max(8, round(theme.min_font_size_frac * short * sc.font_scale))
    m = eng.measurer
    texts = [w.text for w in words]

    def stroke_of(sz):
        return max(1, round(sz * theme.outline_frac))

    while size > min_size and max(m.width(size, t) for t in texts) + 2 * stroke_of(size) > eng.box_w:
        size -= _SIZE_STEP
    stroke = stroke_of(size)
    avail = eng.box_w - 2 * stroke
    widest = max(texts, key=lambda t: m.width(size, t))
    if m.width(size, widest) > avail:
        raise LayoutError(f"word {widest!r} is too wide for the scroll text box at the minimum font size ({size}px)")
    extra = round(size * theme.shadow_extra_frac)
    blur = size * theme.shadow_blur_frac
    sdx, sdy = size * theme.shadow_offset_frac[0], size * theme.shadow_offset_frac[1]
    pad = int(math.ceil(stroke + extra + blur * 3 + max(abs(sdx), abs(sdy)) + 2))
    asc, desc = m.ink_extent(size)
    space = m.width(size, " ")
    widths = [m.width(size, t) for t in texts]

    spans: list[tuple[int, int]] = []
    start, cur = 0, 0.0
    for i, w in enumerate(widths):
        if i > start and (cur + space + w > avail or (sc.break_on_sentence and ends_strong(texts[i - 1]))):
            spans.append((start, i))
            start, cur = i, w
        else:
            cur = w if i == start else cur + space + w
    spans.append((start, len(words)))

    pitch = size * theme.line_spacing
    block_h = asc + desc
    lines: list[ScrollLine] = []
    for li, (a, b) in enumerate(spans):
        lw = sum(widths[a:b]) + space * (b - a - 1)
        if theme.align == "left":
            bx = eng.box_cx - eng.box_w / 2 + stroke
        elif theme.align == "right":
            bx = eng.box_cx + eng.box_w / 2 - stroke - lw
        else:
            bx = eng.box_cx - lw / 2
        ox = int(math.floor(bx)) - pad
        x = bx - math.floor(bx)
        pos = []
        for k in range(a, b):
            pos.append((x, asc))
            x += widths[k] + space
        lay = CaptionLayout(size, (tuple(range(b - a)),), tuple(pos), tuple(widths[a:b]), lw, block_h, stroke, extra, (sdx, sdy), blur, pad,
                            int(math.ceil(lw + 2 * pad + 2)), int(math.ceil(block_h + 2 * pad + 2)), (ox, 0), asc, desc)
        lines.append(ScrollLine(tuple(words[a:b]), a, lay, li * pitch))
    return ScrollLayout(tuple(lines), tuple(words), pitch, size, tuple(l.words[0].start for l in lines))
