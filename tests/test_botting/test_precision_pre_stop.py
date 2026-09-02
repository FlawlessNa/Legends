"""
Tests for the precision pre-stop surviving truncation (issue #100).

Ahead of a precision-sensitive move - a jump or a portal entry, which miss unless the
character is standing still - `compile_movements` releases the held horizontal key so
the chunk after the cut starts from a stopped position. The release was appended as the
last Step and `truncate` was called on the next line; `truncate` copies Steps
`while result.duration < limit` and that branch is only reached once the duration has
already passed the limit, so the release was past the budget by construction and was
never copied. **The pre-stop had never emitted a Step on any path.**

`test_inherited_held_keys.py` pins the *lookup* half of this (issue #97: `keys_held`
was blind to `initial_held_keys`, so the search found nothing to release). This module
pins the *emission*: the keyup reaches the Input Sequence, and it is the last Step.

Nothing here sends real input: every wrapper is compiled with an explicit
`initial_state`, so construction never reads the Held-Keys Ledger.
"""

from collections.abc import Iterator

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from botting.controller.inputs.inputs_helpers import OVERHEAD
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 1234
IGN = "TestChar"

# Both cut points are exercised: 0.5 falls on the walk's very first Step (its delay is
# `FIRST_DELAY`, which alone crosses the budget), 0.9 falls mid-walk with a dozen
# repeats already copied. The pre-stop must emit either way.
TOTAL_DURATIONS = (0.5, 0.9)


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
    total_duration: float | None,
) -> KeyboardInputWrapper:
    """`compile_movements` over the test's fixed handle/ign/speed, minus the `None`."""
    wrapper = compile_movements(
        InputState(held),
        movements=plan,
        handle=HANDLE,
        ign=IGN,
        speed=10.0,
        total_duration=total_duration,
    )
    assert wrapper is not None
    return wrapper


def _h0(wrapper: KeyboardInputWrapper) -> frozenset[str]:
    """The sequence's `H0`. `__post_init__` always resolves `initial_state`."""
    return wrapper.initial_state.held_keys if wrapper.initial_state else frozenset()


def _down_at_end(wrapper: KeyboardInputWrapper) -> set[str]:
    """
    The keys genuinely down when the sequence ends, walked independently of
    `keys_held` and accumulated from `H0` as the catalogue's `down(-1) = H0` requires.
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
    phantoms: list[str] = []
    for key, event in _steps(wrapper):
        if event == "keydown":
            down.add(key)
        elif event == "keyup":
            if key not in down:
                phantoms.append(key)
            down.discard(key)
    return phantoms


def _plan(
    first: _MovementComponent, upcoming: _MovementComponent
) -> tuple[_MovementComponent, ...]:
    """A two-component plan plus the sentinel `pairwise` needs to see `upcoming`."""
    return (first, upcoming, _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0))


_WALK_RIGHT = _MovementComponent(MovementTypes.WALK_RIGHT, 20)
_CLIMB_UP = _MovementComponent(MovementTypes.CLIMB_UP, 20)

# Every member of `_PRECISION_PRE_STOP`, so a member added later without a release is
# a failing test rather than a silent gap.
_PRECISION_UPCOMING = [
    _MovementComponent(MovementTypes.JUMP, 1),
    _MovementComponent(MovementTypes.JUMP_LEFT, 1),
    _MovementComponent(MovementTypes.JUMP_RIGHT, 1),
    _MovementComponent(MovementTypes.JUMP_DOWN, 1),
    _MovementComponent(MovementTypes.ENTER_PORTAL, 1),
]
_PRECISION_IDS = [c.movement_type.name.lower() for c in _PRECISION_UPCOMING]


# --- the emission ---------------------------------------------------------------


@pytest.mark.parametrize("upcoming", _PRECISION_UPCOMING, ids=_PRECISION_IDS)
@pytest.mark.parametrize("total_duration", TOTAL_DURATIONS)
def test_the_pre_stop_release_reaches_the_truncated_sequence(
    upcoming: _MovementComponent, total_duration: float
) -> None:
    """
    The defect in one line: the walk's `right` was still down at the cut, and the
    release meant to stop the character was thrown away by `truncate`.
    """
    wrapper = _compile(frozenset(), _plan(_WALK_RIGHT, upcoming), total_duration)

    assert ("right", "keyup") in list(_steps(wrapper))
    assert "right" not in _down_at_end(wrapper)


@pytest.mark.parametrize("upcoming", _PRECISION_UPCOMING, ids=_PRECISION_IDS)
@pytest.mark.parametrize("total_duration", TOTAL_DURATIONS)
def test_the_pre_stop_release_is_the_last_step(
    upcoming: _MovementComponent, total_duration: float
) -> None:
    """
    Stopped at the cut is the whole point: a Step after the release would move the
    character again before the next chunk's jump or portal entry.
    """
    wrapper = _compile(frozenset(), _plan(_WALK_RIGHT, upcoming), total_duration)

    assert list(_steps(wrapper))[-1] == ("right", "keyup")


@pytest.mark.parametrize("total_duration", TOTAL_DURATIONS)
def test_the_pre_stop_releases_an_inherited_direction(total_duration: float) -> None:
    """
    The lookup half (#97) and the emission half (#100) end to end, which is what
    `test_the_precision_pre_stop_finds_an_inherited_direction` stopped short of. The
    ledger holds `right`, the plan climbs a rope, and no component presses a horizontal
    - so the only way `right` is released before the next chunk's jump is the pre-stop.
    """
    wrapper = _compile(
        frozenset({"right"}),
        _plan(_CLIMB_UP, _MovementComponent(MovementTypes.JUMP_RIGHT, 1)),
        total_duration,
    )

    assert list(_steps(wrapper))[-1] == ("right", "keyup")
    assert "right" not in _down_at_end(wrapper)


# --- what the fix must not broaden ----------------------------------------------


@pytest.mark.parametrize("total_duration", TOTAL_DURATIONS)
def test_a_non_precision_upcoming_move_emits_no_pre_stop(total_duration: float) -> None:
    """
    The release is bought at the cost of stopping the character, so it is only worth
    it ahead of a move that needs a standstill. A walk continues into the next chunk
    with its direction still down.
    """
    wrapper = _compile(
        frozenset(),
        _plan(_WALK_RIGHT, _MovementComponent(MovementTypes.WALK_LEFT, 5)),
        total_duration,
    )

    assert ("right", "keyup") not in list(_steps(wrapper))
    assert "right" in _down_at_end(wrapper)


@pytest.mark.parametrize("upcoming", _PRECISION_UPCOMING, ids=_PRECISION_IDS)
def test_no_pre_stop_when_no_horizontal_is_down(upcoming: _MovementComponent) -> None:
    """
    **A6 No Phantom Release.** A climb with nothing inherited leaves no horizontal
    down, so there is nothing to release and no keyup may be emitted.
    """
    wrapper = _compile(frozenset(), _plan(_CLIMB_UP, upcoming), 0.5)

    assert _phantom_releases(wrapper) == []
    assert not [key for key, event in _steps(wrapper) if event == "keyup"]


@pytest.mark.parametrize("upcoming", _PRECISION_UPCOMING, ids=_PRECISION_IDS)
@pytest.mark.parametrize(
    "held",
    [
        frozenset(),
        frozenset({"left"}),
        frozenset({"right"}),
        frozenset({"up", "right"}),
    ],
)
def test_the_pre_stop_introduces_no_phantom_release(
    upcoming: _MovementComponent, held: frozenset[str]
) -> None:
    """
    **A6 No Phantom Release.** The release now actually reaches the sequence, so for
    the first time it is capable of targeting a key that is not down. It must not:
    the lookup reads the *truncated* copy, whose `keys_held` is what is genuinely down
    at the cut.
    """
    for plan in (_plan(_WALK_RIGHT, upcoming), _plan(_CLIMB_UP, upcoming)):
        wrapper = _compile(held, plan, 0.5)

        assert _phantom_releases(wrapper) == []


# --- the budget -----------------------------------------------------------------


@pytest.mark.parametrize("upcoming", _PRECISION_UPCOMING, ids=_PRECISION_IDS)
@pytest.mark.parametrize("total_duration", TOTAL_DURATIONS)
def test_the_pre_stop_costs_only_its_overhead(
    upcoming: _MovementComponent, total_duration: float
) -> None:
    """
    The release is appended after the cut, so the sequence runs past `total_duration`.
    `truncate` already overshoots - it stops on the Step that *crosses* the limit - and
    the pre-stop must not widen that beyond the single `OVERHEAD` its zero-delay Step
    costs.
    """
    wrapper = _compile(frozenset(), _plan(_WALK_RIGHT, upcoming), total_duration)

    assert wrapper.delays[-1] == 0
    assert wrapper.duration <= total_duration + max(wrapper.delays) + 2 * OVERHEAD
