"""
Tests for **A4 Skill Key Closure** (`docs/planning/movement-invariant-catalogue.md`).

A4: every Hold whose key is non-directional has `t_up` strictly before the sequence
end - a skill key the sequence presses is a key the sequence releases. Direction keys
are deliberately exempt: they carry across a route-cycle boundary on purpose, which is
what stops the character halting and restarting between actions.

A4 was recorded as *holds* and did not (issue #75). `teleport` and `cast_skill` both
`fill` their skill key with keydowns and never emitted the matching keyup, leaving the
key latched to the end of the sequence and released only by the forced volley in
`focused_inputs`' `finally`. The latch outlived the component that made it: a
`teleport -> walk` plan compiled to the teleport key held down for the whole walk.

The volley is a truncation safety net, not the normal release path, so the fix put the
keyup in the builders. In `teleport` it is guarded on the key actually being down,
because `fill` stops on *absolute* sequence duration and can legitimately emit no Step
at all - and a keyup for a key never pressed is the phantom release **A6** forbids.
`cast_skill` needed the same guard until issue #98 made its keydown unconditional; the
window arithmetic that made an empty fill possible there is pinned in
`test_cast_window.py`.

Nothing here sends real input: every sequence is compiled against an explicit
`initial_held_keys`, and no handle refers to a real window.
"""

from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from maple.actions import movements_v2
from maple.actions.skills_related_v2 import cast_skill
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 4321
IGN = "TestChar"
TELEPORT_KEY = "shift"
DIRECTIONS = frozenset({"left", "right", "up", "down"})


@dataclass(frozen=True)
class _StubSkill(MapleSkill):
    """A `Skill` whose key bind does not go through the keybindings config."""

    key: str = field(default="", repr=False)

    # Decorated like the base's `key_bind`: `Skill.key_bind` is itself `@lru_cache`d,
    # so a plain-method override is an incompatible override to Pyright. B019 warns
    # about per-instance cache lifetime, which a frozen test stub does not have.
    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


TELEPORT = _StubSkill("Teleport", "Movement", key=TELEPORT_KEY, animation_time=0.6)
ULTIMATE = _StubSkill("Genesis", "Attack", key="d", animation_time=1.0)
# Shorter than a single filled Step. Since issue #98 `cast_skill` presses once anyway,
# so even this compiles to a matched keydown/keyup pair rather than to nothing.
INSTANT = _StubSkill("Instant", "Attack", key="f", animation_time=0.05)


def _steps(wrapper: KeyboardInputWrapper) -> Iterator[tuple[str, str]]:
    """Yields one `(key, event)` pair per key in each Step, in Step order."""
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list) and isinstance(events, list):
            yield from zip(keys, events)
        elif isinstance(keys, str) and isinstance(events, str):
            yield keys, events


def _latched(wrapper: KeyboardInputWrapper) -> set[str]:
    """
    The non-directional keys still down at the sequence end - exactly the Holds A4
    forbids. Accumulated from `initial_held_keys`, as the catalogue's `down(-1) = H0`
    requires.
    """
    down = set(wrapper.initial_held_keys or ())
    for key, event in _steps(wrapper):
        if event == "keydown":
            down.add(key)
        elif event == "keyup":
            down.discard(key)
    return {key for key in down if key not in DIRECTIONS}


def _held_at(wrapper: KeyboardInputWrapper, index: int) -> set[str]:
    """Every key down immediately after Step `index`."""
    down = set(wrapper.initial_held_keys or ())
    for step, (keys, events) in enumerate(zip(wrapper.keys, wrapper.events)):
        pairs = zip(keys, events) if isinstance(keys, list) else [(keys, events)]
        for key, event in pairs:
            if event == "keydown":
                down.add(key)
            elif event == "keyup":
                down.discard(key)
        if step == index:
            break
    return down


def _compile(*components: _MovementComponent) -> KeyboardInputWrapper:
    """Compiles a Movement Plan against nothing held, terminated as the planner does."""
    plan = components + (_MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),)
    sequence = compile_movements(
        frozenset(),
        movements=plan,
        handle=HANDLE,
        ign=IGN,
        speed=1.0,
        teleport=TELEPORT,
    )
    assert sequence is not None, "every plan here compiles to at least one Step"
    return sequence


# --- the defect ----------------------------------------------------------------


def test_teleport_releases_its_skill_key_within_the_sequence() -> None:
    """Load-bearing: the fill used to end with the teleport key still down."""
    sequence = _compile(_MovementComponent(MovementTypes.TELEPORT_RIGHT, 3))
    assert _latched(sequence) == set()


def test_teleport_does_not_hold_its_skill_key_into_the_following_component() -> None:
    """
    The latch outlived its component: a `teleport -> walk` plan held the teleport key
    down for the whole 5-unit walk. Asserted at the walk's own Steps, not just at the
    end, so a fix that only released the key last would still be red here.
    """
    sequence = _compile(
        _MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),
        _MovementComponent(MovementTypes.WALK_RIGHT, 5),
    )
    walk_steps = [
        index
        for index, key in enumerate(sequence.keys)
        if key == "right" and sequence.events[index] == "keydown"
    ]
    # The walk is the long tail of `right` keydowns; take its final Step.
    assert TELEPORT_KEY not in _held_at(sequence, walk_steps[-1])


def test_cast_skill_releases_its_skill_key_within_the_sequence() -> None:
    """`cast_skill` had the identical hole; #75's body claimed teleport was alone."""
    sequence = cast_skill(HANDLE, IGN, ULTIMATE, initial_held_keys=frozenset())
    assert _latched(sequence) == set()


@pytest.mark.parametrize("direction", [None, "left", "right"])
def test_cast_skill_closes_its_hold_for_every_direction(direction: str | None) -> None:
    sequence = cast_skill(
        HANDLE, IGN, ULTIMATE, direction=direction, initial_held_keys=frozenset()
    )
    assert _latched(sequence) == set()


# --- the guard -----------------------------------------------------------------


def test_a_window_too_short_to_fill_still_pairs_its_press_and_release() -> None:
    """
    An `animation_time` below one Step's cost leaves `fill` nothing to emit. This used
    to mean no skill key at all - the keyup guarded away to avoid the phantom release
    **A6** forbids, and the skill silently uncast. Issue #98 presses once regardless,
    which closes both: the pair is matched, so A4 holds and A6 has no exposure here.
    """
    sequence = cast_skill(
        HANDLE, IGN, INSTANT, direction="left", initial_held_keys=frozenset()
    )
    pressed = [key for key, event in _steps(sequence) if event == "keydown"]
    released = [key for key, event in _steps(sequence) if event == "keyup"]
    assert pressed.count(INSTANT.key) == 1
    assert released.count(INSTANT.key) == 1
    assert _latched(sequence) == set()


# --- direction keys stay exempt ------------------------------------------------


def test_a_downward_teleport_still_carries_its_direction_key() -> None:
    """`down` is left held on purpose and declared for forced release; A4 exempts it."""
    sequence = _compile(_MovementComponent(MovementTypes.TELEPORT_DOWN, 1))
    assert "down" in sequence.keys_held
    assert _latched(sequence) == set()


def test_the_repeat_key_shape_still_carries_up_into_the_climb() -> None:
    """
    Handed a `repeat_key`, `teleport` releases its skill key and fills `up` instead,
    arriving at the rope already holding it. A direction latch, deliberately kept.
    """
    sequence = movements_v2.teleport(
        HANDLE,
        IGN,
        "right",
        TELEPORT,
        num_times=2,
        repeat_key="up",
        initial_held_keys=frozenset(),
    )
    assert "up" in sequence.keys_held
    assert _latched(sequence) == set()


# --- the rule holds across the plans the lab will compile -----------------------


@pytest.mark.parametrize(
    "components",
    [
        (_MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),),
        (_MovementComponent(MovementTypes.TELEPORT_LEFT, 1),),
        (_MovementComponent(MovementTypes.TELEPORT_UP, 2),),
        (
            _MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),
            _MovementComponent(MovementTypes.WALK_RIGHT, 5),
        ),
        (
            _MovementComponent(MovementTypes.WALK_RIGHT, 5),
            _MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),
        ),
        (
            _MovementComponent(MovementTypes.TELEPORT_RIGHT, 2),
            _MovementComponent(MovementTypes.TELEPORT_UP, 2),
        ),
    ],
    ids=["tp3", "tp_left", "tp_up", "tp_then_walk", "walk_then_tp", "tp_then_tp"],
)
def test_no_plan_latches_a_skill_key(
    components: tuple[_MovementComponent, ...],
) -> None:
    assert _latched(_compile(*components)) == set()


@pytest.mark.parametrize(
    "components",
    [
        (_MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),),
        (_MovementComponent(MovementTypes.TELEPORT_DOWN, 1),),
        (
            _MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),
            _MovementComponent(MovementTypes.WALK_RIGHT, 5),
        ),
    ],
    ids=["tp3", "tp_down", "tp_then_walk"],
)
def test_terminal_release_holds_for_the_same_plans(
    components: tuple[_MovementComponent, ...],
) -> None:
    """
    **A2 Terminal Release** - whatever is still down at the end is declared for forced
    release. A4's resolution leans on A2 covering the tail case, so the two are pinned
    together here; the catalogue had A2 recorded as failing against a closed ticket.
    """
    sequence = _compile(*components)
    assert sequence.keys_held <= set(sequence.forced_key_releases)
