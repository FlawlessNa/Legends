"""
Tests for issue #129: the precision pre-stop wired to fire on the edge-departure
flag (PM3), unconditionally rather than as a side effect of truncation.

`test_precision_pre_stop.py` pins the existing mechanism: `_PRECISION_PRE_STOP`
only ever inserts a release when `total_duration` happens to truncate the compile
right before a jump or portal entry. An edge departure is a plan-time property of
the *upcoming* component (`_MovementComponent.edge_departure`), so the stop it wants
must fire every time that component is about to be built - truncated or not, and for
`TELEPORT_*` as much as `JUMP_*`, neither of which the pre-existing mechanism reaches.

Nothing here sends real input: every wrapper is built with an explicit `initial_state`,
and `key_binds` is stubbed (as `test_movement_provenance.py` does) because
`configs/keybindings.ini` is a personal config no checkout is guaranteed to have -
needed here, unlike `test_precision_pre_stop.py`, because several cases compile a jump
for real rather than only truncating up to one.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics import movement_mechanics_v2
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 1234
IGN = "TestChar"
JUMP_KEY = "space"


@pytest.fixture(autouse=True)
def jump_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stubs the key bind lookup - see `test_movement_provenance.py`'s fixture of the
    same name."""
    monkeypatch.setattr(
        movement_mechanics_v2, "key_binds", lambda ign: {"jump": JUMP_KEY}
    )


@dataclass(frozen=True)
class _StubSkill(MapleSkill):
    """A `Skill` whose key bind does not go through the keybindings config -
    mirrors `test_telecast.py`'s `_StubSkill`."""

    key: str = field(default="", repr=False)

    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


TELEPORT_SKILL = _StubSkill("Teleport", "Movement", key="shift", animation_time=0.6)

_WALK_RIGHT = _MovementComponent(MovementTypes.WALK_RIGHT, 20)
_EDGE_JUMP_RIGHT = _MovementComponent(MovementTypes.JUMP_RIGHT, 1, edge_departure=True)
_PLAIN_JUMP_RIGHT = _MovementComponent(MovementTypes.JUMP_RIGHT, 1)
_EDGE_TELEPORT_RIGHT = _MovementComponent(
    MovementTypes.TELEPORT_RIGHT, 1, edge_departure=True
)
_PLAIN_TELEPORT_RIGHT = _MovementComponent(MovementTypes.TELEPORT_RIGHT, 1)

# Origins in every `_plan(first, upcoming)` below: `first` is component 0, `upcoming`
# is component 1. A directional jump/teleport re-presses its own direction key from a
# stopped position (see `single_jump`'s `keys_held` check), so a pre-stop release is
# not "no `right` again" - it is "released while attributed to the walk (origin 0),
# not to the jump/teleport (origin 1) or to the terminal cleanup (`NO_COMPONENT`)".
_WALK_ORIGIN, _UPCOMING_ORIGIN = 0, 1


def _steps(wrapper: KeyboardInputWrapper) -> Iterator[tuple[str, str]]:
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list) and isinstance(events, list):
            yield from zip(keys, events)
        elif isinstance(keys, str) and isinstance(events, str):
            yield keys, events


def _steps_with_origin(
    wrapper: KeyboardInputWrapper,
) -> Iterator[tuple[str, str, int]]:
    """Like `_steps`, but carrying each Step's Provenance origin (#102) - what
    distinguishes a release this ticket's mechanism produced from one the terminal
    cleanup or the pre-existing `_PRECISION_PRE_STOP` branch produced."""
    for keys, events, origin in zip(wrapper.keys, wrapper.events, wrapper.origins):
        if isinstance(keys, list) and isinstance(events, list):
            yield from ((key, event, origin) for key, event in zip(keys, events))
        elif isinstance(keys, str) and isinstance(events, str):
            yield keys, events, origin


def _plan(
    first: _MovementComponent, upcoming: _MovementComponent
) -> tuple[_MovementComponent, ...]:
    return (first, upcoming, _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0))


def _compile(
    plan: tuple[_MovementComponent, ...],
    total_duration: float | None,
    teleport: MapleSkill | None = None,
) -> KeyboardInputWrapper:
    wrapper = compile_movements(
        InputState(frozenset()),
        movements=plan,
        handle=HANDLE,
        ign=IGN,
        speed=10.0,
        teleport=teleport,
        total_duration=total_duration,
    )
    assert wrapper is not None
    return wrapper


# --- fires with no truncation at all ----------------------------------------------


def test_edge_departure_pre_stop_fires_with_no_truncation() -> None:
    """
    No `total_duration` cap, so `compile_movements` never enters the truncation
    branch at all - `_PRECISION_PRE_STOP` could never fire here. The edge-departure
    flag must still stop the walk before the jump.
    """
    wrapper = _compile(_plan(_WALK_RIGHT, _EDGE_JUMP_RIGHT), total_duration=None)

    assert ("right", "keyup") in list(_steps(wrapper))


def test_edge_departure_pre_stop_release_precedes_the_flagged_component() -> None:
    """
    The release belongs to the walk, not the jump: it is attributed to the walk's
    own origin, and lands before any Step the jump component produced - including
    the jump's own fresh `right` keydown, which `single_jump` presses again because
    the pre-stop left nothing held to travel on.
    """
    wrapper = _compile(_plan(_WALK_RIGHT, _EDGE_JUMP_RIGHT), total_duration=None)

    steps = list(_steps_with_origin(wrapper))
    release_index = next(
        i
        for i, (key, event, origin) in enumerate(steps)
        if (key, event, origin) == ("right", "keyup", _WALK_ORIGIN)
    )
    first_jump_step = next(
        i for i, (_, _, origin) in enumerate(steps) if origin == _UPCOMING_ORIGIN
    )
    assert release_index < first_jump_step


def test_no_pre_stop_without_the_edge_departure_flag() -> None:
    """
    The same upcoming move type, unflagged, must not gain a stop it never had - this
    mechanism must not silently widen `_PRECISION_PRE_STOP`'s scope. `right` is still
    released eventually (the terminal cleanup, `NO_COMPONENT`), but never on the
    walk's own origin - the signature a pre-stop release carries.
    """
    wrapper = _compile(_plan(_WALK_RIGHT, _PLAIN_JUMP_RIGHT), total_duration=None)

    assert ("right", "keyup", _WALK_ORIGIN) not in list(_steps_with_origin(wrapper))


# --- extends to TELEPORT_*, which _PRECISION_PRE_STOP never covered --------------


def test_edge_departure_pre_stop_fires_for_teleport() -> None:
    """
    `_PRECISION_PRE_STOP` is jumps and `ENTER_PORTAL` only; a `TELEPORT_*` never
    triggered the truncation-time pre-stop regardless of flags. The edge-departure
    flag must reach it independently.
    """
    wrapper = _compile(
        _plan(_WALK_RIGHT, _EDGE_TELEPORT_RIGHT),
        total_duration=None,
        teleport=TELEPORT_SKILL,
    )

    assert ("right", "keyup") in list(_steps(wrapper))


def test_no_pre_stop_for_an_unflagged_teleport() -> None:
    wrapper = _compile(
        _plan(_WALK_RIGHT, _PLAIN_TELEPORT_RIGHT),
        total_duration=None,
        teleport=TELEPORT_SKILL,
    )

    assert ("right", "keyup", _WALK_ORIGIN) not in list(_steps_with_origin(wrapper))


# --- fires at truncation too, where TELEPORT_* was never reached before ----------


def test_edge_departure_pre_stop_fires_when_truncation_lands_there() -> None:
    """
    The cut landing right before an edge-departure `TELEPORT_*` is the one case
    `_PRECISION_PRE_STOP` structurally cannot cover (teleport is not a member), so
    this is the regression #129 exists to close.
    """
    wrapper = _compile(
        _plan(_WALK_RIGHT, _EDGE_TELEPORT_RIGHT),
        total_duration=0.5,
        teleport=TELEPORT_SKILL,
    )

    assert ("right", "keyup") in list(_steps(wrapper))
    assert list(_steps(wrapper))[-1] == ("right", "keyup")


def test_edge_departure_and_precision_pre_stop_do_not_double_release() -> None:
    """
    `JUMP_RIGHT` is in both `_PRECISION_PRE_STOP` and (when flagged) edge-departure.
    Truncating right before one must release `right` exactly once, not twice.
    """
    wrapper = _compile(_plan(_WALK_RIGHT, _EDGE_JUMP_RIGHT), total_duration=0.5)

    releases = [(key, event) for key, event in _steps(wrapper) if event == "keyup"]
    assert releases.count(("right", "keyup")) == 1
