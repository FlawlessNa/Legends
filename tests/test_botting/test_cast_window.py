"""
Tests for `cast_skill`'s cast window (issue #98).

`fill` stops on **absolute** sequence duration, and `cast_skill` handed it a raw
`skill.animation_time`. Two defects fell out of that, and both are pinned here:

- The direction Steps `cast_skill` appends first were spent out of the cast's own
  budget, so a directed cast filled for less time than an undirected one - and for a
  short enough `animation_time` the fill emitted nothing and the skill was never cast.
  Every other `fill` call site passes a delta; this one now does too.
- The fill ran to the limit and the closing keyup was appended *after* it, so the skill
  key was still down when the animation completed and the game auto-repeated a second
  cast - the repo owner's live observation. The fill now reserves one Step's worth of
  the window so the keyup is sent strictly inside it.

Timings are asserted against `DELAY` and `OVERHEAD` symbolically, never as literals:
`OVERHEAD` is measured at import time and differs per machine and per run.

Nothing here sends real input: every sequence is compiled against an explicit
`initial_state`, and no handle refers to a real window.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import pytest

from botting.controller import DELAY, OVERHEAD
from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from maple.actions.skills_related_v2 import cast_skill
from maple.model.characters.maple_skills import MapleSkill

HANDLE = 4321
IGN = "TestChar"


@dataclass(frozen=True)
class _StubSkill(MapleSkill):
    """A `Skill` whose key bind does not go through the keybindings config."""

    key: str = field(default="", repr=False)

    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


ULTIMATE = _StubSkill("Genesis", "Attack", key="d", animation_time=1.0)
# Shorter than a single filled Step, let alone the direction Steps ahead of it.
INSTANT = _StubSkill("Instant", "Attack", key="f", animation_time=0.05)


def _sent_at(wrapper: KeyboardInputWrapper, index: int) -> float:
    """
    The sequence time at which Step `index` is sent. Each Step is sent, *then* its delay
    is awaited, so a Step goes out at the cumulative duration of everything before it -
    the same accounting as `KeyboardInputWrapper.duration`.
    """
    return sum(wrapper.delays[:index]) + OVERHEAD * index


def _skill_steps(wrapper: KeyboardInputWrapper, key: str) -> list[tuple[int, str]]:
    """`(index, event)` for every Step carrying `key`, in Step order."""
    return [
        (index, event)
        for index, (step_key, event) in enumerate(zip(wrapper.keys, wrapper.events))
        if step_key == key and isinstance(event, str)
    ]


# --- the window is a delta, not an absolute ------------------------------------


@pytest.mark.parametrize("direction", ["left", "right"])
def test_the_direction_steps_are_not_spent_out_of_the_cast_window(
    direction: str,
) -> None:
    """
    Load-bearing. The setup Steps used to count against the fill's absolute limit, so a
    directed cast held the skill key for measurably less than an undirected one.
    """
    undirected = cast_skill(HANDLE, IGN, ULTIMATE, initial_state=InputState())
    directed = cast_skill(
        HANDLE, IGN, ULTIMATE, direction=direction, initial_state=InputState()
    )

    def _held_for(wrapper: KeyboardInputWrapper) -> float:
        steps = _skill_steps(wrapper, ULTIMATE.key)
        return _sent_at(wrapper, steps[-1][0]) - _sent_at(wrapper, steps[0][0])

    # Both fill the same window; only the random jitter of one Step separates them.
    assert _held_for(directed) == pytest.approx(_held_for(undirected), abs=2 * DELAY)


def test_a_short_animation_still_casts_the_skill() -> None:
    """
    Load-bearing. With an absolute limit the direction Steps exhausted the whole window
    and the fill emitted nothing: `cast_skill` compiled to two Steps, neither of them
    the skill key, and the skill was never cast at all.
    """
    sequence = cast_skill(
        HANDLE, IGN, INSTANT, direction="left", initial_state=InputState()
    )
    events = [event for _, event in _skill_steps(sequence, INSTANT.key)]
    assert events[:1] == ["keydown"], "the skill is pressed at least once"
    assert events[-1] == "keyup", "and released within the sequence"


# --- the keyup lands inside the window -----------------------------------------


@pytest.mark.parametrize("direction", [None, "left", "right"])
def test_the_skill_key_comes_up_before_the_animation_completes(
    direction: str | None,
) -> None:
    """
    Load-bearing. The fill ran until the sequence duration reached the limit and the
    keyup was appended after that, so it was sent at or past the moment the first cast
    completed - and the key still being down there is what triggers the second cast.
    """
    sequence = cast_skill(
        HANDLE, IGN, ULTIMATE, direction=direction, initial_state=InputState()
    )
    steps = _skill_steps(sequence, ULTIMATE.key)
    first_down, keyup = steps[0][0], steps[-1][0]
    assert steps[-1][1] == "keyup"
    deadline = _sent_at(sequence, first_down) + ULTIMATE.animation_time
    assert _sent_at(sequence, keyup) < deadline


def test_the_window_is_not_given_away_wholesale() -> None:
    """
    The reservation is one Step, not a free-floating margin: the fill must still cover
    almost the whole animation, or the auto-repeat it exists to sustain breaks down.
    """
    sequence = cast_skill(HANDLE, IGN, ULTIMATE, initial_state=InputState())
    steps = _skill_steps(sequence, ULTIMATE.key)
    first_down, keyup = steps[0][0], steps[-1][0]
    held_for = _sent_at(sequence, keyup) - _sent_at(sequence, first_down)
    assert held_for > ULTIMATE.animation_time - 3 * (DELAY + OVERHEAD)
