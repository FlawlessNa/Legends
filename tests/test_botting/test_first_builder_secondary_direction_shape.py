"""
Tests for **A1 Shape** and **A2 Terminal Release**
(`docs/planning/movement-invariant-catalogue.md`), for the case issue #113 named:
`move`'s `structure is None` branch (the plan's first builder call) opening with a
`secondary_direction`.

That branch used to flatten the simultaneous two-key batch into two separate Steps
(`first_keys`) while keeping a single `[first_delay]` - so the wrapper it built had
`len(keys) == len(events) == 2` but `len(delays) == 1`, an **A1** violation. Every
`zip(keys, events, delays)` (`truncate` included) silently dropped the Step that
overran `delays`, which - for an untruncated sequence - is always the terminal
release volley, so the drop doubled as an **A2** violation: `focused_inputs`' send
loop indexes `delays[i]` for `i in range(len(inputs))` and raises `IndexError`
reaching it live.

Only fires when both hold: `structure is None` (the plan's first component) and
`secondary_direction` is set - `compile_movements` reaches this from a `WALK_*`
whose upcoming move is `ENTER_PORTAL`/`CLIMB_UP`/`CLIMB_DOWN`, or a `CLIMB_*` whose
upcoming move is a `WALK_*`.

Nothing here sends real input: every sequence is compiled against an explicit
`initial_state`, and no handle refers to a real window.
"""

from collections.abc import Iterator
from typing import Any

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from maple.actions import movements_v2
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 1234
IGN = "TestChar"


def _steps(wrapper: KeyboardInputWrapper) -> Iterator[tuple[str, Any]]:
    """Yields one `(key, event)` pair per key in each Step, in Step order."""
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list):
            yield from zip(keys, events)
        else:
            yield keys, events


def _down_after_last_step(wrapper: KeyboardInputWrapper) -> set[str]:
    """`down(n-1)`: the held set accumulated from `H0` through every Step."""
    h0 = wrapper.initial_state.held_keys if wrapper.initial_state else frozenset()
    down = set(h0)
    for key, event in _steps(wrapper):
        if event == "keydown":
            down.add(key)
        elif event == "keyup":
            down.discard(key)
    return down


def _assert_shape(wrapper: KeyboardInputWrapper) -> None:
    """A1: one delay per Step, keys and events aligned."""
    assert len(wrapper.keys) == len(wrapper.events) == len(wrapper.delays)
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list):
            assert isinstance(events, list)
            assert len(keys) == len(events)
        else:
            assert isinstance(events, str)


# --- A1 Shape, direct repro from the ticket -------------------------------------


def test_move_opening_with_a_secondary_direction_keeps_shape_parity() -> None:
    """
    The ticket's own repro: `move(..., "right", "up", ...)` with no `structure` and
    no held keys used to give `keys: 5, events: 5, delays: 4`.
    """
    wrapper = movements_v2.move(
        HANDLE,
        "right",
        "up",
        duration=0.6,
        initial_state=InputState(frozenset()),
    )

    _assert_shape(wrapper)


def test_the_opening_pair_is_two_separate_steps_not_one_batch() -> None:
    """
    Pins the shape actually chosen (one delay per flattened Step) rather than the
    rival (one batched two-key Step): the two keys are separate Step entries, the
    first carrying the typematic delay and the second the ordinary input cadence.
    """
    wrapper = movements_v2.move(
        HANDLE,
        "right",
        "up",
        duration=0.6,
        initial_state=InputState(frozenset()),
    )

    assert wrapper.keys[0] == "right"
    assert wrapper.keys[1] == "up"
    assert wrapper.delays[0] == movements_v2.FIRST_DELAY


# --- A1 Shape, through compile_movements ----------------------------------------


def test_a_walk_opening_the_plan_into_a_portal_keeps_shape_parity() -> None:
    """
    `compile_movements` reaches the defective branch from a `WALK_*` whose upcoming
    move is `ENTER_PORTAL` - the untruncated repro from the ticket
    (`WALK_RIGHT 20, ENTER_PORTAL 1, END`) used to give 51 keys / 50 delays.
    """
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 20),
        _MovementComponent(MovementTypes.ENTER_PORTAL, 1),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    wrapper = compile_movements(
        InputState(), movements=plan, handle=HANDLE, ign=IGN, speed=10.0
    )

    assert wrapper is not None
    _assert_shape(wrapper)


def test_a_climb_opening_the_plan_into_a_walk_keeps_shape_parity() -> None:
    """The other side named in the ticket: a `CLIMB_*` whose upcoming move is a `WALK_*`."""
    plan = (
        _MovementComponent(MovementTypes.CLIMB_UP, 10),
        _MovementComponent(MovementTypes.WALK_RIGHT, 5),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    wrapper = compile_movements(
        InputState(), movements=plan, handle=HANDLE, ign=IGN, speed=10.0
    )

    assert wrapper is not None
    _assert_shape(wrapper)


# --- A2 Terminal Release ----------------------------------------------------------


def test_the_terminal_release_step_is_not_dropped() -> None:
    """
    A2: for an untruncated sequence, `down(n-1)` is a subset of `forced_key_releases`.
    The dropped Step was always this one - the release volley `for...else` appends
    once compilation runs to completion - so the shape defect doubled as an A2
    violation whenever it fired.
    """
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 20),
        _MovementComponent(MovementTypes.ENTER_PORTAL, 1),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    wrapper = compile_movements(
        InputState(), movements=plan, handle=HANDLE, ign=IGN, speed=10.0
    )

    assert wrapper is not None
    still_down = _down_after_last_step(wrapper)
    assert still_down <= set(wrapper.forced_key_releases)


def test_a_zip_based_consumer_does_not_silently_drop_the_terminal_release() -> None:
    """
    `focused_inputs.KeyboardInputWrapper.truncate` walks
    `zip(self.keys, self.events, self.delays, self.origins)`: with one fewer delay
    than keys/events, zip stops one Step short regardless of `limit`, silently
    handing back a shorter sequence than intended - the "offline / truncated"
    failure the ticket names, distinct from the live `IndexError`.
    """
    plan = (
        _MovementComponent(MovementTypes.WALK_RIGHT, 20),
        _MovementComponent(MovementTypes.ENTER_PORTAL, 1),
        _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
    )

    wrapper = compile_movements(
        InputState(), movements=plan, handle=HANDLE, ign=IGN, speed=10.0
    )
    assert wrapper is not None

    # A limit well past the sequence's own duration: nothing should be cut, only
    # copied - so a shorter result means the copy dropped a Step, not that it cut one.
    copy = wrapper.truncate(wrapper.duration + 10.0)

    assert len(copy.keys) == len(wrapper.keys)
    still_down = _down_after_last_step(copy)
    assert still_down <= set(copy.forced_key_releases)
