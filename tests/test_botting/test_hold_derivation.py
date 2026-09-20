"""
Tests for `KeyboardInputWrapper.holds` - the catalogue's **Hold** derivation
(`docs/planning/movement-invariant-catalogue.md`, implementation requirement 1).

A Hold is `(key, t_down, t_up)`, half-open over `[t_down, t_up)`. `t_down` is `0.0`
for a key already down entering the sequence (`H0`), exactly the accumulation
`keys_held` performs while discarding the timing; `t_up` is the sequence end
(`wrapper.duration`) for a key never released. `toolkit/movement_timeline._parse_intervals`
used to walk the Steps on its own to build this same table for the Gantt tool; its body
is now this property, so there is one traversal and one source of truth.

Nothing here sends real input: every wrapper is built with an explicit `initial_state`,
so construction never reads the Held-Keys Ledger.
"""

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from botting.controller.inputs.inputs_helpers import OVERHEAD

HANDLE = 1234
NOBODY = InputState(frozenset())


def test_a_pressed_and_released_key_holds_from_its_keydown_to_its_keyup() -> None:
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "right"],
        ["keydown", "keyup"],
        [0.5, 0.0],
        initial_state=NOBODY,
    )

    t_down = 0.0
    t_up = 0.5 + OVERHEAD
    assert wrapper.holds == {"right": [(t_down, t_up)]}


def test_a_key_never_released_holds_until_the_sequence_end() -> None:
    wrapper = KeyboardInputWrapper(
        HANDLE, ["right"], ["keydown"], [0.5], initial_state=NOBODY
    )

    assert wrapper.holds == {"right": [(0.0, wrapper.duration)]}


def test_a_key_already_down_entering_the_sequence_opens_its_hold_at_zero() -> None:
    """H0 carries no timestamp of its own - the sequence's own origin is what a Hold
    that started before it can be anchored to."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["jump"],
        ["keydown"],
        [0.2],
        initial_state=InputState(frozenset({"right"})),
    )

    assert wrapper.holds["right"] == [(0.0, wrapper.duration)]


def test_an_inherited_key_released_mid_sequence_closes_at_the_release() -> None:
    """Step 0 is sent at `t(0) = 0` regardless of its own delay - the delay is the
    wait *after* it, not before."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right"],
        ["keyup"],
        [0.5],
        initial_state=InputState(frozenset({"right"})),
    )

    assert wrapper.holds == {"right": [(0.0, 0.0)]}


def test_a_key_pressed_released_and_pressed_again_reports_two_holds() -> None:
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "right", "right"],
        ["keydown", "keyup", "keydown"],
        [0.1, 0.1, 0.0],
        initial_state=NOBODY,
    )

    assert list(wrapper.holds) == ["right"]
    holds = wrapper.holds["right"]
    assert len(holds) == 2
    first_up = 0.1 + OVERHEAD
    second_down = first_up + 0.1 + OVERHEAD
    assert holds[0] == pytest.approx((0.0, first_up))
    assert holds[1] == pytest.approx((second_down, wrapper.duration))


def test_simultaneous_keys_in_one_step_share_the_same_timestamp() -> None:
    """Two non-opposing keys pressed in the same batch - `_clear_opposites` has
    nothing to insert, so the Step lands exactly as given."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        [["jump", "shift"]],
        [["keydown", "keydown"]],
        [0.2],
        initial_state=NOBODY,
    )

    assert wrapper.holds["jump"] == [(0.0, wrapper.duration)]
    assert wrapper.holds["shift"] == [(0.0, wrapper.duration)]


def test_holds_agrees_with_keys_held_on_which_keys_are_still_down() -> None:
    """One traversal, one source of truth: whichever keys `keys_held` reports are the
    ones whose last Hold closes at `duration`, and no others."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "jump", "jump"],
        ["keydown", "keydown", "keyup"],
        [0.1, 0.2, 0.1],
        initial_state=NOBODY,
    )

    still_down = {
        key
        for key, intervals in wrapper.holds.items()
        if intervals[-1][1] == wrapper.duration
    }
    assert still_down == wrapper.keys_held
