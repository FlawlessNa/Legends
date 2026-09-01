"""
Tests for **A6 No Phantom Release** (`docs/planning/movement-invariant-catalogue.md`).

A6: for every keyup of key `k` at Step `i`, `k` is in `down(i-1)` - the held set
accumulated from `initial_state.held_keys`. A human never releases a key they are not
holding, and the pattern is machine-distinguishable, so a release with no matching
press is a humanization defect.

`KeyboardInputWrapper.__post_init__` used to insert a `left` keyup whenever `right`
was desired (and vice versa) whether or not it was down - a blunt guard against a
stale direction latching the character, standing in for compile-time held-keys state
nobody trusted. The Held-Keys Ledger made that state authoritative, so the guard is
gone (issue #28) and these tests pin its absence.

Nothing here sends real input: every wrapper is built with an explicit
`initial_state`, so construction never reads the ledger.
"""

from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from botting.models_abstractions.base_skill import Skill
from maple.actions import movements_v2
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 1234
IGN = "TestChar"
JUMP_KEY = "space"


class _StubSkill:
    """Duck-types the subset of `Skill` the teleport builder uses in tests."""

    animation_time = 0.05

    @staticmethod
    def key_bind(ign: str) -> str:
        return "shift"


def _steps(wrapper: KeyboardInputWrapper) -> Iterator[tuple[str, Any]]:
    """Yields one `(key, event)` pair per key in each Step, in Step order."""
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list):
            yield from zip(keys, events)
        else:
            yield keys, events


def _h0(wrapper: KeyboardInputWrapper) -> frozenset[str]:
    """The sequence's `H0`. `__post_init__` always resolves `initial_state`."""
    return wrapper.initial_state.held_keys if wrapper.initial_state else frozenset()


def _phantom_releases(wrapper: KeyboardInputWrapper) -> list[str]:
    """
    Walks the Input Sequence exactly as A6 states it, accumulating the held set from
    `initial_state.held_keys`, and reports every keyup targeting a key that is not down.
    """
    down = set(_h0(wrapper))
    phantoms = []
    for key, event in _steps(wrapper):
        if event == "keydown":
            down.add(key)
        elif event == "keyup":
            if key not in down:
                phantoms.append(key)
            down.discard(key)
    return phantoms


# --- construction --------------------------------------------------------------


def test_construction_inserts_no_release_when_the_opposite_is_not_held() -> None:
    """The defect: this used to open with a `left` keyup nobody had pressed."""
    wrapper = KeyboardInputWrapper(
        HANDLE, ["right"], ["keydown"], [0.0], initial_state=InputState()
    )

    assert wrapper.keys == ["right"]
    assert wrapper.events == ["keydown"]
    assert _phantom_releases(wrapper) == []


def test_construction_reading_the_ledger_also_inserts_nothing(
    held_movement_keys: Callable[..., None],
) -> None:
    """
    The live path resolves held keys instead of being handed them, and lands in the
    same place: nothing held, nothing released.
    """
    held_movement_keys()

    wrapper = KeyboardInputWrapper(HANDLE, ["right"], ["keydown"], [0.0])

    assert wrapper.keys == ["right"]


def test_construction_releases_the_opposite_it_finds_held() -> None:
    """
    Removing the blind release must not cost the real one: an opposing direction
    that *is* down still gets a keyup, ahead of the Step that opposes it (A3).
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right"],
        ["keydown"],
        [0.0],
        initial_state=InputState(frozenset({"left"})),
    )

    assert wrapper.keys[0] == ["left"]
    assert wrapper.events[0] == ["keyup"]
    assert wrapper.keys[1:] == ["right"]
    assert _phantom_releases(wrapper) == []


def test_construction_releases_a_held_up_when_down_is_desired() -> None:
    """The vertical pair was never covered by the blind release, and is unchanged."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["down"],
        ["keydown"],
        [0.0],
        initial_state=InputState(frozenset({"up"})),
    )

    assert wrapper.keys[0] == ["up"]
    assert wrapper.events[0] == ["keyup"]


def test_appending_an_opposing_direction_releases_the_one_the_sequence_holds() -> None:
    """
    Opposites are cleared as the sequence grows too, off the in-sequence held state
    rather than the inherited one.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE, ["right"], ["keydown"], [0.0], initial_state=InputState()
    )

    wrapper.append("left", "keydown", 0.0)

    assert list(_steps(wrapper)) == [
        ("right", "keydown"),
        ("right", "keyup"),
        ("left", "keydown"),
    ]
    assert _phantom_releases(wrapper) == []


# --- A6 over the movement builders ---------------------------------------------


def _walk(held: frozenset) -> KeyboardInputWrapper:
    return movements_v2.move(
        HANDLE,
        "right",
        duration=0.3,
        release_keys=["up", "down"],
        initial_state=InputState(held),
    )


def _jump(held: frozenset) -> KeyboardInputWrapper:
    return movements_v2.single_jump(
        HANDLE, "right", JUMP_KEY, initial_state=InputState(held)
    )


def _rope(held: frozenset) -> KeyboardInputWrapper:
    return movements_v2.jump_on_rope(
        HANDLE, "right", JUMP_KEY, initial_state=InputState(held)
    )


def _teleport(held: frozenset) -> KeyboardInputWrapper:
    return movements_v2.teleport(
        HANDLE,
        IGN,
        "right",
        cast(Skill, _StubSkill()),
        initial_state=InputState(held),
    )


@pytest.mark.parametrize("builder", [_walk, _jump, _rope, _teleport])
@pytest.mark.parametrize(
    "held",
    [
        frozenset(),
        frozenset({"left"}),
        frozenset({"right"}),
        frozenset({"up"}),
        frozenset({"left", "up"}),
    ],
)
def test_builders_never_release_a_key_that_is_not_down(
    builder: Callable[[frozenset[str]], KeyboardInputWrapper], held: frozenset[str]
) -> None:
    """A6 across every held state a builder can inherit."""
    assert _phantom_releases(builder(held)) == []


def test_a_walk_with_nothing_held_emits_no_release_at_all() -> None:
    """
    Sharper than A6 for the case the defect was about: with an empty held set the
    walk is pure keydowns, so there is nothing for a humanization check to see.
    """
    wrapper = _walk(frozenset())

    assert {event for _, event in _steps(wrapper)} == {"keydown"}


def test_a_walk_opposing_an_inherited_direction_still_releases_it_once() -> None:
    """The guard the blind release was standing in for, done off real state."""
    wrapper = _walk(frozenset({"left"}))

    releases = [key for key, event in _steps(wrapper) if event == "keyup"]
    assert releases == ["left"]


# --- A6 over a compiled Movement Plan ------------------------------------------


_PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 10),
    _MovementComponent(MovementTypes.CLIMB_UP, 5),
    _MovementComponent(MovementTypes.WALK_LEFT, 8),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)


_REVERSAL = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 3),
    _MovementComponent(MovementTypes.WALK_LEFT, 3),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)


def test_reversing_direction_releases_the_first_direction_before_pressing_it_again() -> (
    None
):
    """
    Regression on the insertion index: the opposite-key release used to be inserted
    at `-1`, landing *ahead of* the keydown it was meant to clear. A plan that walks
    right then left compiled to `right keyup, right keydown, left keydown` - a
    phantom release (A6), and both directions down afterwards (A3).
    """
    wrapper = compile_movements(
        InputState(), movements=_REVERSAL, handle=HANDLE, ign=IGN, speed=10.0
    )
    assert wrapper is not None

    assert list(_steps(wrapper))[:3] == [
        ("right", "keydown"),
        ("right", "keyup"),
        ("left", "keydown"),
    ]
    assert _phantom_releases(wrapper) == []


@pytest.mark.parametrize(
    "held",
    [frozenset(), frozenset({"left"}), frozenset({"right"}), frozenset({"up", "left"})],
)
def test_a_compiled_plan_never_releases_a_key_it_never_pressed(
    held: frozenset[str],
) -> None:
    """
    End to end, through the same `compile_movements` the live path and the offline
    lab both call - several components, so releases inserted between them count too.
    """
    wrapper = compile_movements(
        InputState(held), movements=_PLAN, handle=HANDLE, ign=IGN, speed=10.0
    )
    assert wrapper is not None

    assert _phantom_releases(wrapper) == []
