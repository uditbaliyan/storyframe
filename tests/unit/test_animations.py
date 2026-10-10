import pytest

from storyframe.animations import plan_animation, state_at
from storyframe.config import AnimationConfig
from storyframe.models import CaptionGroup, Word
from storyframe.timeline import schedule_groups


def grp(dur=1.0, nxt=None):
    gs = [CaptionGroup((Word("a", 1.0, 1.0 + dur),))]
    if nxt:
        gs.append(CaptionGroup((Word("b", nxt, nxt + 0.5),)))
    return schedule_groups(gs, 0.12, 0.1)[0]


def test_fade_in_progresses_and_completes():
    cfg, g = AnimationConfig(), grp()
    p = plan_animation(g, cfg, "fade")
    assert state_at(p, g, 1.0, cfg, 1920).alpha == 0
    assert 0 < state_at(p, g, 1.0 + p.dur_in / 2, cfg, 1920).alpha < 1
    assert state_at(p, g, 1.0 + p.dur_in + 0.01, cfg, 1920).is_identity


def test_slide_up_moves_and_pop_scales_without_overshoot():
    cfg, g = AnimationConfig(), grp()
    s = state_at(plan_animation(g, cfg, "slide_up"), g, 1.0, cfg, 1920)
    assert s.dy == pytest.approx(0.03 * 1920)
    sp = state_at(plan_animation(g, cfg, "pop"), g, 1.02, cfg, 1920)
    assert cfg.pop_start_scale <= sp.scale <= 1.0


def test_reduced_motion_and_static():
    g = grp()
    rm = AnimationConfig(reduced_motion=True)
    s = state_at(plan_animation(g, rm, "slide_up"), g, 1.02, rm, 1920)
    assert s.dy == 0 and s.scale == 1 and s.alpha < 1
    assert state_at(plan_animation(g, rm, "none"), g, 1.0, rm, 1920).is_identity


def test_short_groups_get_short_animations():
    g = grp(dur=0.1)
    assert plan_animation(g, AnimationConfig(entrance_duration=0.5), "fade").dur_in <= 0.035 + 1e-9


def test_exit_fades_after_last_word_not_before():
    cfg, g = AnimationConfig(), grp(nxt=9.0)
    p = plan_animation(g, cfg, "fade")
    assert p.fade_out_start >= g.end
    assert state_at(p, g, g.end - 0.01, cfg, 1920).alpha == 1
    assert state_at(p, g, p.visible_end, cfg, 1920).alpha == pytest.approx(0)


def test_animation_never_changes_active_word_time():
    """Active-word lookup takes only time; animation state has no influence on it."""
    from storyframe.timeline import active_word_index
    g = CaptionGroup((Word("a", 1.0, 1.2), Word("b", 1.2, 1.5)))
    assert [active_word_index(g, t) for t in (1.0, 1.19, 1.2, 1.49)] == [0, 0, 1, 1]
