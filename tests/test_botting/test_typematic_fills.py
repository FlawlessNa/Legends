"""
Tests for the fills that repeat a key without owning typematic (issue #99), the exact
truncation that replacing them needs, and the delay-only Step that carries their time.

[#109](https://github.com/FlawlessNa/Legends/issues/109) made **A7 Typematic Legality**
decidable by carrying `T0` into compilation. This is the other half: three builders were
emitting runs of keydowns for a key that did not own typematic, which is input no human
produces. The rule, from Spy++ on a live client - a keydown claims ownership, a later
keydown takes it, and any keyup ends repetition outright rather than handing it back.

A fill is legal exactly when its own first Step is a genuine press. Where it is not, the
key stays down and its budget rides on one delay-only Step: the game follows key *state*,
not repeat messages, so the character moves either way.

Nothing here sends real input. Every `KeyboardInputWrapper` is handed an explicit
`initial_state`, so construction never reads the ledger.
"""

from dataclasses import dataclass, field
from functools import lru_cache

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from botting.controller.inputs.inputs_helpers import OVERHEAD, TYPEMATIC_REPEAT
from maple.actions import movements_v2 as mv
from maple.model.characters.maple_skills import MapleSkill

HANDLE = 1234
IGN = "TestMage"
TELEPORT_KEY = "shift"
JUMP_KEY = "alt"

NOBODY = InputState(frozenset(), None, 0.0)
RIGHT_HELD_NO_OWNER = InputState(frozenset({"right"}), None, 0.0)
RIGHT_HELD_AND_OWNING = InputState(frozenset({"right"}), "right", 0.6)


@dataclass(frozen=True)
class _StubSkill(MapleSkill):
    """A `Skill` whose key bind does not go through the keybindings config."""

    key: str = field(default="", repr=False)

    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


TELEPORT_SKILL = _StubSkill(
    "Teleport", "Movement", key=TELEPORT_KEY, animation_time=0.6
)


def _steps(wrapper: KeyboardInputWrapper) -> list[tuple[object, object]]:
    return list(zip(wrapper.keys, wrapper.events))


def _pairs(keys: object, events: object) -> list[tuple[str, str]]:
    """One Step's `(key, event)` pairs, whether it carries a single key or a batch."""
    if isinstance(keys, list) and isinstance(events, list):
        return [(str(key), str(event)) for key, event in zip(keys, events)]
    return [(str(keys), str(events))]


def _a7_violations(wrapper: KeyboardInputWrapper) -> list[tuple[int, str]]:
    """
    Every Step that repeats a key it does not own - the A7 check, run from `H0`/`T0`.

    A keydown for a key already down is a repeat; one for a key that is not is a press,
    and claims ownership. Any keyup drops ownership outright.
    """
    state = wrapper.initial_state
    assert state is not None
    down = set(state.held_keys)
    owner = state.typematic_owner
    violations: list[tuple[int, str]] = []
    for idx, (keys, events) in enumerate(_steps(wrapper)):
        for key, event in _pairs(keys, events):
            if event == "keydown":
                if key in down and owner != key:
                    violations.append((idx, key))
                down.add(key)
                owner = key
            elif event == "keyup":
                down.discard(key)
                owner = None
    return violations


def _keydowns_of(wrapper: KeyboardInputWrapper, key: str) -> int:
    return sum(
        1
        for keys, events in _steps(wrapper)
        for k, e in _pairs(keys, events)
        if k == key and e == "keydown"
    )


def _delay_only_steps(wrapper: KeyboardInputWrapper) -> list[int]:
    return [idx for idx, (keys, _) in enumerate(_steps(wrapper)) if keys == []]


# --- move: the Continuation case ---------------------------------------------------


def test_a_continuation_walk_emits_no_repeat_of_the_inherited_direction() -> None:
    """
    `right` is down but a teleport took ownership and dropped it, so nothing may repeat
    it. Before #99 this compiled to a run of `right keydown` Steps at the input cadence.
    """
    wrapper = mv.move(HANDLE, "right", duration=2.0, initial_state=RIGHT_HELD_NO_OWNER)

    assert _keydowns_of(wrapper, "right") == 0
    assert _a7_violations(wrapper) == []


def test_a_continuation_walk_carries_its_budget_on_one_delay_only_step() -> None:
    wrapper = mv.move(HANDLE, "right", duration=2.0, initial_state=RIGHT_HELD_NO_OWNER)

    assert _delay_only_steps(wrapper) == [0]
    assert wrapper.duration == pytest.approx(2.0, abs=1e-6)


def test_a_continuation_walk_leaves_the_direction_held() -> None:
    """The character keeps walking off the still-held key; only the repeats are gone."""
    wrapper = mv.move(HANDLE, "right", duration=2.0, initial_state=RIGHT_HELD_NO_OWNER)

    assert "right" in wrapper.keys_held


def test_a_walk_whose_direction_owns_typematic_still_repeats() -> None:
    """The legal case must survive: this is what a human's held key actually produces."""
    wrapper = mv.move(
        HANDLE, "right", duration=1.0, initial_state=RIGHT_HELD_AND_OWNING
    )

    assert _keydowns_of(wrapper, "right") > 1
    assert _a7_violations(wrapper) == []
    assert _delay_only_steps(wrapper) == []


def test_a_fresh_walk_presses_once_and_then_repeats() -> None:
    wrapper = mv.move(HANDLE, "right", duration=1.0, initial_state=NOBODY)

    assert _keydowns_of(wrapper, "right") > 1
    assert _a7_violations(wrapper) == []
    assert wrapper.typematic_owner == "right"


# --- the other two builders --------------------------------------------------------


def test_teleport_repeat_key_emits_no_repeat_after_the_skill_keyup() -> None:
    """
    The textbook violation: direction down, teleport down, teleport **up**, then a fill.
    Spy++ says nothing repeats after that keyup, whatever is still held.
    """
    wrapper = mv.teleport(
        HANDLE,
        IGN,
        "up",
        TELEPORT_SKILL,
        num_times=2,
        repeat_key="up",
        initial_state=InputState(frozenset({"up"}), None, 0.0),
    )

    assert _a7_violations(wrapper) == []


def test_single_jump_repeat_key_still_presses_when_the_key_is_not_held() -> None:
    """
    The rope catch: `up` is not down, so the fill's first Step is a genuine press and
    every Step after it is a legal repeat. Silencing this would stop catching ropes.
    """
    wrapper = mv.single_jump(
        HANDLE, "right", JUMP_KEY, repeat_key="up", initial_state=NOBODY
    )

    assert _keydowns_of(wrapper, "up") > 1
    assert _a7_violations(wrapper) == []


def test_single_jump_repeat_key_stays_silent_when_the_key_is_already_held() -> None:
    """Arriving at a rope already holding `up`, with the jump key owning typematic."""
    wrapper = mv.single_jump(
        HANDLE,
        "right",
        JUMP_KEY,
        repeat_key="up",
        initial_state=InputState(frozenset({"right", "up"}), None, 0.0),
    )

    assert _keydowns_of(wrapper, "up") == 0
    assert _a7_violations(wrapper) == []


# --- A1: the opening press of a walk into a climb ----------------------------------


def test_a_two_key_opening_press_gives_every_step_its_own_delay() -> None:
    """
    A walk carrying a secondary direction, as the *first* builder of a plan, built two
    Steps against one delay - an **A1 Shape** violation, and an IndexError on `delays[i]`
    in the send loop. Reachable whenever a walk into a climb or a portal opens a plan.
    """
    wrapper = mv.move(HANDLE, "left", "up", duration=1.0, initial_state=NOBODY)

    assert len(wrapper.keys) == len(wrapper.events) == len(wrapper.delays)


# --- truncate cuts the delay, not the Step -----------------------------------------


def test_truncate_lands_exactly_on_the_limit_for_a_single_long_step() -> None:
    """
    The case that made chunking look necessary: one 5s Step cut at 1s used to come back
    whole, a 5x overshoot.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE, [[]], [[]], [5.0], initial_state=RIGHT_HELD_NO_OWNER
    )

    assert wrapper.truncate(1.0).duration == pytest.approx(1.0, abs=1e-9)


def test_truncate_lands_exactly_on_the_limit_for_a_multi_step_walk() -> None:
    wrapper = mv.move(HANDLE, "right", duration=3.0, initial_state=NOBODY)

    assert wrapper.truncate(1.0).duration == pytest.approx(1.0, abs=1e-9)


def test_truncate_keeps_the_step_whose_delay_it_trims() -> None:
    """The keydown still reaches the game; only the wait after it is shortened."""
    wrapper = KeyboardInputWrapper(
        HANDLE, ["right"], ["keydown"], [5.0], initial_state=NOBODY
    )

    truncated = wrapper.truncate(1.0)

    assert truncated.keys == ["right"]
    assert truncated.events == ["keydown"]


def test_truncate_never_emits_a_negative_delay() -> None:
    """**A5 Delays**: the trim clamps at zero rather than borrowing from the Step."""
    wrapper = KeyboardInputWrapper(
        HANDLE, ["right"], ["keydown"], [0.001], initial_state=NOBODY
    )

    truncated = wrapper.truncate(0.0005)

    assert all(delay >= 0 for delay in truncated.delays)


def test_truncate_leaves_a_sequence_shorter_than_the_limit_alone() -> None:
    wrapper = mv.move(HANDLE, "right", duration=0.6, initial_state=NOBODY)

    assert wrapper.truncate(5.0).duration == pytest.approx(wrapper.duration, abs=1e-9)


# --- the delay-only Step ------------------------------------------------------------


def test_a_delay_only_step_sends_nothing() -> None:
    """`SendInput(0, ...)` is a no-op returning 0 - the count `_send_input` checks for."""
    wrapper = KeyboardInputWrapper(
        HANDLE, [[]], [[]], [1.0], initial_state=RIGHT_HELD_NO_OWNER
    )

    assert int(wrapper.c_input[0][0].value) == 0


def test_a_delay_only_step_changes_neither_held_keys_nor_ownership() -> None:
    wrapper = KeyboardInputWrapper(
        HANDLE, [[]], [[]], [1.0], initial_state=RIGHT_HELD_AND_OWNING
    )

    assert wrapper.keys_held == {"right"}
    assert wrapper.typematic_owner == "right"


def test_a_delay_only_step_satisfies_a1_shape() -> None:
    wrapper = KeyboardInputWrapper(HANDLE, [[]], [[]], [1.0], initial_state=NOBODY)

    assert len(wrapper.keys) == len(wrapper.events) == len(wrapper.delays)


# --- B6: the cadence the repeats are spaced at --------------------------------------


def test_repeats_are_spaced_at_the_measured_typematic_interval() -> None:
    """
    **B6 Repeat Cadence** is stated over *wall-clock* spacing, and the send loop spends
    `OVERHEAD` on top of every delay it is handed. Asking for 33ms therefore delivered
    33ms + OVERHEAD, a rate no Windows typematic setting produces.
    """
    wrapper = mv.move(
        HANDLE, "right", duration=2.0, initial_state=RIGHT_HELD_AND_OWNING
    )

    gaps = [delay + OVERHEAD for delay in wrapper.delays[1:]]

    assert gaps
    for gap in gaps:
        assert gap == pytest.approx(TYPEMATIC_REPEAT, rel=0.06)
