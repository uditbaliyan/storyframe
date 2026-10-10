"""Pure-Python/numpy frame compositor: background + one caption sprite per frame (cached per visual state)."""
from __future__ import annotations

from bisect import bisect_right

import numpy as np
from PIL import Image

from ..animations import plan_animation, state_at
from ..timeline import active_word_index, revealed_count
from ..typography import FontMeasurer, Sprite, draw_caption
from .background import breathe_gain, build_background
from .base import RenderPlan


class FrameCompositor:
    def __init__(self, plan: RenderPlan):
        self.plan = plan
        cfg = plan.config
        self.W, self.H = cfg.width, cfg.height
        self.bg, self.bg_spec = build_background(plan.theme.background, cfg.background, self.W, self.H, cfg.seed)
        self._bg_cache: dict[int, np.ndarray] = {}
        self.starts = [g.start for g in plan.groups]
        self.anims = [plan_animation(g, cfg.animation, plan.entrance) for g in plan.groups]
        self.measurer = FontMeasurer(plan.font_path)
        self._sprite_group = -1
        self._scroll_sprites: dict[tuple[int, int], Sprite] = {}
        self._word_starts = [w.start for w in plan.scroll.words] if plan.scroll is not None else []
        self._sprites: dict[tuple[int, int], Sprite] = {}

    def sample_time(self, n: int) -> float:
        """Frame n is displayed over [n/fps, (n+1)/fps); sample at its midpoint to centre sync error."""
        return (n + 0.5) / self.plan.config.fps

    def _background(self, t: float) -> np.ndarray:
        g = breathe_gain(self.bg_spec, t)
        key = round(g * 1024)
        arr = self._bg_cache.get(key)
        if arr is None:
            if key == 1024:
                arr = self.bg
            else:
                lut = np.clip(np.arange(256) * (key / 1024.0) + 0.5, 0, 255).astype(np.uint8)
                arr = lut[self.bg]
            self._bg_cache[key] = arr
        return arr.copy()

    def _sprite(self, gi: int, active: int, revealed: int) -> Sprite:
        if gi != self._sprite_group:
            self._sprites.clear()
            self._sprite_group = gi
        key = (active, revealed)
        sp = self._sprites.get(key)
        if sp is None:
            g, lay = self.plan.groups[gi], self.plan.layouts[gi]
            texts = [w.text for w in g.words]
            sp = draw_caption(lay, texts, self.measurer.font(lay.font_size), self.plan.theme, [i < revealed for i in range(len(texts))], active)
            self._sprites[key] = sp
        return sp

    def caption_state(self, t: float):
        """(group_index, active_word_index, revealed_count) at time t, or None when nothing is shown."""
        i = bisect_right(self.starts, t) - 1
        if i < 0:
            return None
        g = self.plan.groups[i]
        if t >= g.visible_end:
            return None
        active = active_word_index(g, t) if self.plan.config.highlight_active_word else -1
        revealed = revealed_count(g, t) if self.plan.entrance == "word_reveal" else len(g.words)
        return i, active, revealed

    def frame_at(self, t: float) -> np.ndarray:
        if self.plan.scroll is not None:
            return self._frame_scroll(t)
        frame = self._background(t)
        st = self.caption_state(t)
        if st is None:
            return frame
        gi, active, revealed = st
        sprite = self._sprite(gi, active, revealed)
        a = state_at(self.anims[gi], self.plan.groups[gi], t, self.plan.config.animation, self.H)
        if a.alpha <= 0:
            return frame
        ox, oy = self.plan.layouts[gi].origin
        if a.scale != 1.0:
            w, h = sprite.size
            nw, nh = max(1, round(w * a.scale)), max(1, round(h * a.scale))
            sprite = Sprite(sprite.image.resize((nw, nh), Image.BILINEAR))
            ox, oy = round(ox + (w - nw) / 2), round(oy + (h - nh) / 2)
        self._blend(frame, sprite, ox, round(oy + a.dy), a.alpha)
        return frame

    def _blend(self, frame: np.ndarray, sprite: Sprite, x: int, y: int, gain: float) -> None:
        prem, alpha = sprite.arrays()
        h, w = alpha.shape[:2]
        x0, y0, x1, y1 = max(x, 0), max(y, 0), min(x + w, self.W), min(y + h, self.H)
        if x1 <= x0 or y1 <= y0:
            return
        sp = prem[y0 - y:y1 - y, x0 - x:x1 - x]
        sa = alpha[y0 - y:y1 - y, x0 - x:x1 - x]
        region = frame[y0:y1, x0:x1].astype(np.float32)
        out = region * (1.0 - sa * gain) + sp * gain
        frame[y0:y1, x0:x1] = np.clip(out + 0.5, 0, 255).astype(np.uint8)

    # ---- scroll (teleprompter) mode -------------------------------------------------------------------------
    def _scroll_sprite(self, li: int, active: int) -> Sprite:
        key = (li, active)
        sp = self._scroll_sprites.get(key)
        if sp is None:
            if len(self._scroll_sprites) > 96:
                self._scroll_sprites.clear()
            line = self.plan.scroll.lines[li]
            lay = line.layout
            texts = [w.text for w in line.words]
            sp = draw_caption(lay, texts, self.measurer.font(lay.font_size), self.plan.theme, [True] * len(texts), active)
            self._scroll_sprites[key] = sp
        return sp

    def _frame_scroll(self, t: float) -> np.ndarray:
        frame = self._background(t)
        plan, sl = self.plan, self.plan.scroll
        cfg, sc, th = plan.config, plan.config.scroll, plan.theme
        words = sl.words
        a = cfg.animation
        fade_in = 0.3
        alpha = min(max((t - (words[0].start - fade_in)) / fade_in, 0.0), 1.0)
        tail = a.linger + max(a.exit_duration, 0.1) * 2
        out_start = words[-1].end + a.linger
        alpha *= 1.0 - min(max((t - out_start) / (tail - a.linger), 0.0), 1.0)
        if alpha <= 0:
            return frame
        i = bisect_right(self._word_starts, t) - 1
        active = i if (cfg.highlight_active_word and i >= 0 and t < words[i].end) else -1
        H = self.H
        win_h = min(sc.window_height * H, H * (1 - 2 * th.safe_margin_frac))
        win_top = th.box_center_y_frac * H - win_h / 2
        focus_y = win_top + sc.focus * win_h
        fz = max(sc.fade_edge * win_h, 1.0)
        s = sl.offset_at(t, sc.duration, sc.easing)
        for li, line in enumerate(sl.lines):
            cy = focus_y + line.y - s
            g = min(max((cy - win_top) / fz, 0.0), 1.0) * min(max((win_top + win_h - cy) / fz, 0.0), 1.0)
            if g <= 0.01:
                continue
            local = active - line.first if line.first <= active < line.first + len(line.words) else -1
            lay = line.layout
            self._blend(frame, self._scroll_sprite(li, local), lay.origin[0], round(cy - lay.block_h / 2 - lay.pad), alpha * g)
        return frame
