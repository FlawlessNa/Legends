"""
Tests for `KeyboardInputWrapper.keys_held` reporting inherited state (issue #97).

The catalogue defines the held set as accumulating from `H0`: `down(-1) = H0`, where
`H0` is the sequence's `initial_state.held_keys`. `keys_held` is meant to be `down(n-1)`,
but it walked `self.keys`/`self.events` from an **empty** set, so every key the
Held-Keys Ledger reported at the sequence's start was invisible to it.

`_resolve_held_keys` (`movements_v2.py`) returns that property whenever a structure
already exists, which is every builder after the first in a Movement Plan. So the
ledger's state reached the first builder and was then dropped, and three catalogue
entries the suite marks as holding did not:

- **C3 No Inherited Stuck Key** - the end-of-sequence release walks `keys_held`, so an
  inherited direction no component pressed was never released and stayed down past the
  sequence.
- **C2 Boundary Opposing Release** / **A3 No Opposing Overlap** - `append` clears
  opposites against `keys_held`, so pressing `left` while the ledger held `right` left
  both directions down.
- The **precision pre-stop** (`movement_mechanics_v2.py`) searches `keys_held` for a
  horizontal key to release before a precision-sensitive jump, and found nothing.

Nothing here sends real input: every wrapper is built with an explicit
`initial_state`, so construction never reads the ledger.
"""

from collections.abc import Iterator

import pytest

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
JUMP_KEY = "space"
DIRECTIONS = ("left", "right", "up", "down")


def _steps(wrapper: KeyboardInputWrapper) -> Iterator[tuple[str, str]]:
    """Yields one `(key, event)` pair per key in each Step, in Step order."""
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list) and isinstance(events, list):
            yield from zip(keys, events)
        elif isinstance(keys, str) and isinstance(events, str):
            yield keys, events


def _compile(
    held: frozenset[str],
    plan: tuple[_MovementComponent, ...],
    always_release: bool = False,
) -> KeyboardInputWrapper:
    """`compile_movements` over the test's fixed handle/ign/speed, minus the `None`."""
    wrapper = compile_movements(
        InputState(held),
        movements=plan,
        handle=HANDLE,
        ign=IGN,
        speed=10.0,
        always_release=always_release,
    )
    assert wrapper is not None
    return wrapper


def _h0(wrapper: KeyboardInputWrapper) -> frozenset[str]:
    """The sequence's `H0`. `__post_init__` always resolves `initial_state`."""
    return wrapper.initial_state.held_keys if wrapper.initial_state else frozenset()


def _down_at_end(wrapper: KeyboardInputWrapper) -> set[str]:
    """
    The keys genuinely down when the sequence ends, walked independently of the
    property under test and accumulated from `H0` as the catalogue's `down(-1) = H0`
    requires. This is what `keys_held` is supposed to return.
    """
    down = set(_h0(wrapper))
    for key, event in _steps(wrapper):
        if event == "keydown":
            down.add(key)
        elif event == "keyup":
            down.discard(key)
    return down


def _phantom_releases(wrapper: KeyboardInputWrapper) -> list[str]:
    """A6: every keyup must target a key that is down. Guards the fix's blast radius."""
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


def _both_horizontals_ever_down(wrapper: KeyboardInputWrapper) -> bool:
    """A3: no Hold of `left` may overlap a Hold of `right`."""
    down = set(_h0(wrapper))
    for key, event in _steps(wrapper):
        if event == "keydown":
            down.add(key)
        elif event == "keyup":
            down.discard(key)
        if {"left", "right"} <= down:
            return True
    return False


# --- the property itself --------------------------------------------------------


def test_keys_held_reports_an_inherited_key_no_step_touches() -> None:
    """The defect in one line: the ledger held `right` and the property said nothing."""
    wrapper = KeyboardInputWrapper(
        HANDLE, initial_state=InputState(frozenset({"right"}))
    )

    assert wrapper.keys_held == {"right"}


def test_keys_held_reports_an_inherited_key_alongside_a_pressed_one() -> None:
    """The ticket's second line: pressing `shift` used to erase `right` from view."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["shift"],
        ["keydown"],
        [0.0],
        initial_state=InputState(frozenset({"right"})),
    )

    assert wrapper.keys_held == {"right", "shift"}


def test_keys_held_drops_an_inherited_key_the_sequence_releases() -> None:
    """
    Seeding must not latch: a keyup cancels an inherited key exactly as it cancels a
    key the sequence pressed itself. Without this the property would over-report.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right"],
        ["keyup"],
        [0.0],
        initial_state=InputState(frozenset({"right"})),
    )

    assert wrapper.keys_held == set()


def test_keys_held_is_unchanged_when_nothing_is_inherited() -> None:
    """Regression guard: the empty-`H0` case is the one that always worked."""
    wrapper = KeyboardInputWrapper(
        HANDLE, ["right"], ["keydown"], [0.0], initial_state=InputState()
    )

    assert wrapper.keys_held == {"right"}


def test_truncate_carries_the_inherited_state_to_the_copy() -> None:
    """
    `truncate` builds a fresh wrapper; the cut sequence inherits the same `H0`, so the
    copy must report the inherited key too rather than starting blind.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["up", "up"],
        ["keydown", "keydown"],
        [0.1, 0.1],
        initial_state=InputState(frozenset({"right"})),
    )

    assert wrapper.truncate(0.05).keys_held == {"right", "up"}


# --- what the builders read through `_resolve_held_keys` ------------------------


def test_a_later_builder_still_sees_the_inherited_direction() -> None:
    """
    `_resolve_held_keys` returns `structure.keys_held` once a structure exists, which
    is every builder after the first. That is where the ledger's state was dropped.
    """
    structure = KeyboardInputWrapper(
        HANDLE,
        ["up"],
        ["keydown"],
        [0.0],
        initial_state=InputState(frozenset({"right"})),
    )

    assert movements_v2._resolve_held_keys(structure, HANDLE, None) == {"right", "up"}


def test_jump_on_rope_does_not_re_press_an_inherited_direction() -> None:
    """
    `jump_on_rope` branches on `direction in structure.keys_held`. Blind, it took the
    `else` branch and pressed `right` again while `right` was already down.
    """
    structure = KeyboardInputWrapper(
        HANDLE,
        ["up"],
        ["keydown"],
        [0.0],
        initial_state=InputState(frozenset({"right"})),
    )

    result = movements_v2.jump_on_rope(HANDLE, "right", JUMP_KEY, structure=structure)

    presses = [key for key, event in _steps(result) if event == "keydown"]
    assert presses.count("right") == 0


# --- C3: the inherited direction must not survive the sequence ------------------


_CLIMB_THEN_PORTAL = (
    _MovementComponent(MovementTypes.CLIMB_UP, 5),
    _MovementComponent(MovementTypes.ENTER_PORTAL, 1),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)

_CLIMB_THEN_WALK_LEFT = (
    _MovementComponent(MovementTypes.CLIMB_UP, 5),
    _MovementComponent(MovementTypes.CLIMB_UP, 5),
    _MovementComponent(MovementTypes.WALK_LEFT, 5),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)


def test_a_plan_releases_an_inherited_direction_no_component_presses() -> None:
    """
    **C3 No Inherited Stuck Key.** The ticket's stated repro: ledger holds `right`, the
    plan starts with `CLIMB_UP`. `right` is neither used nor released, so the character
    kept walking right through the whole climb and past the sequence end.
    """
    wrapper = _compile(frozenset({"right"}), _CLIMB_THEN_PORTAL)

    assert "right" not in _down_at_end(wrapper)


def test_pressing_the_opposite_of_an_inherited_direction_releases_it_first() -> None:
    """
    **C2 Boundary Opposing Release** and **A3 No Opposing Overlap**. `append` cleared
    opposites against a blind `keys_held`, so the `left` keydown went in with `right`
    still down and both horizontals were held at once.
    """
    wrapper = _compile(frozenset({"right"}), _CLIMB_THEN_WALK_LEFT)

    assert not _both_horizontals_ever_down(wrapper)
    keyups = [key for key, event in _steps(wrapper) if event == "keyup"]
    assert "right" in keyups


# --- the precision pre-stop -----------------------------------------------------


def test_the_precision_pre_stop_finds_an_inherited_direction() -> None:
    """
    `movement_mechanics_v2` searches `keys_held` for a horizontal key to release before
    truncating ahead of a precision-sensitive move, so the next chunk starts stopped.
    Blind, the search found nothing and the character entered the portal still moving.

    This pins the *lookup*, not the emitted keyup, and deliberately so: the pre-stop's
    release is appended once `structure.duration` has already reached `total_duration`,
    so the `truncate` on the next line always discards it. That is a second, separate
    defect - it bites identically when the direction was pressed by the sequence rather
    than inherited - and is tracked on its own ticket. Asserting the release end to end
    here would be asserting that ticket's fix, not this one's.
    """
    structure = KeyboardInputWrapper(
        HANDLE,
        ["up"],
        ["keydown"],
        [0.5],
        initial_state=InputState(frozenset({"right"})),
    )

    held_dir = next((k for k in structure.keys_held if k in ("left", "right")), None)
    assert held_dir == "right"


def test_always_release_covers_an_inherited_direction() -> None:
    """
    `always_release` promises every key still held at the end reaches
    `forced_key_releases`. An inherited direction is still held, so it belongs there.
    """
    wrapper = _compile(frozenset({"right"}), _CLIMB_THEN_PORTAL, always_release=True)

    assert "right" in wrapper.forced_key_releases or "right" not in _down_at_end(
        wrapper
    )


# --- A6 must survive the fix ----------------------------------------------------


@pytest.mark.parametrize(
    "plan", [_CLIMB_THEN_PORTAL, _CLIMB_THEN_WALK_LEFT], ids=["portal", "walk_left"]
)
@pytest.mark.parametrize(
    "held",
    [
        frozenset(),
        frozenset({"left"}),
        frozenset({"right"}),
        frozenset({"up", "right"}),
    ],
)
def test_seeding_introduces_no_phantom_release(
    plan: tuple[_MovementComponent, ...], held: frozenset[str]
) -> None:
    """
    **A6 No Phantom Release.** Seeding makes `keys_held` report more keys, and every
    consumer that releases what it finds there is now capable of emitting a keyup the
    sequence never pressed. It must not: the inherited keys are genuinely down.
    """
    wrapper = _compile(held, plan)

    assert _phantom_releases(wrapper) == []
