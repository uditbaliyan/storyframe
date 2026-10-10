"""Caption animation timing. Animations only alter alpha/offset/scale of an already laid-out caption;
they never change which word is active (that is derived from MFA intervals in timeline.py)."""
from __future__ import annotations

from dataclasses import dataclass

from .config import AnimationConfig
from .models import CaptionGroup


def _lin(p): return p
def _out_quad(p): return 1 - (1 - p) ** 2
def _out_cubic(p): return 1 - (1 - p) ** 3
def _io_cubic(p): return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


EASINGS = {"linear": _lin, "ease_out_quad": _out_quad, "ease_out_cubic": _out_cubic, "ease_in_out_cubic": _io_cubic}


@dataclass(frozen=True)
class AnimState:
    alpha: float = 1.0
    dy: float = 0.0  # pixels, positive = down
    scale: float = 1.0

    @property
    def is_identity(self) -> bool:
        return self.alpha == 1.0 and self.dy == 0.0 and self.scale == 1.0


@dataclass(frozen=True)
class GroupAnimation:
    kind: str
    dur_in: float
    dur_out: float
    fade_out_start: float
    visible_end: float


def plan_animation(group: CaptionGroup, cfg: AnimationConfig, kind: str) -> GroupAnimation:
    """Short groups get shorter transitions so brief words never trigger long animations."""
    assert group.visible_end is not None, "schedule_groups() must run first"
    if kind == "none":
        return GroupAnimation(kind, 0.0, 0.0, group.visible_end, group.visible_end)
    dur_in = min(cfg.entrance_duration, 0.35 * max(group.duration, 1e-3))
    if kind == "word_reveal":
        dur_in = min(dur_in, 0.08)
    post = max(group.visible_end - group.end, 0.0)
    dur_out = min(cfg.exit_duration, post)
    return GroupAnimation(kind, dur_in, dur_out, group.visible_end - dur_out, group.visible_end)


def state_at(plan: GroupAnimation, group: CaptionGroup, t: float, cfg: AnimationConfig, frame_h: int) -> AnimState:
    if plan.kind == "none":
        return AnimState()
    ease = EASINGS[cfg.easing]
    alpha, dy, scale = 1.0, 0.0, 1.0
    if plan.dur_in > 0 and t < group.start + plan.dur_in:
        p = ease(min(max((t - group.start) / plan.dur_in, 0.0), 1.0))
        alpha = p
        if not cfg.reduced_motion:
            if plan.kind == "slide_up":
                dy = (1 - p) * cfg.slide_distance * frame_h
            elif plan.kind == "pop":
                scale = cfg.pop_start_scale + (1 - cfg.pop_start_scale) * p
                alpha = min(1.0, p * 1.6)
    if plan.dur_out > 0 and t > plan.fade_out_start:
        q = min(max((t - plan.fade_out_start) / plan.dur_out, 0.0), 1.0)
        alpha *= 1 - q
    return AnimState(alpha, dy, scale)
