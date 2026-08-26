"""
Tests for telecast - fusing an ultimate cast into a movement's teleport keydowns.

Telecast used to introspect the Input Sequence a DecisionMaker had already compiled.
Dispatch-time compilation (ADR 0002) removed that sequence from the Engine process,
so the transform now runs at dispatch, wrapped around the movement compiler rather
than folded into it. These tests pin the rebuild itself - the count and spacing of the
paired presses that replace a teleport region - the wrapper's contract at the compiler
seam including the fallback when nothing turns out to be fusable, and the invariants a
skill key pressed inside a movement sequence has to keep satisfying (catalogue A2, A6,
D1).

Nothing here sends real input: every sequence is compiled offline against an explicit
`initial_held_keys`, and no handle refers to a real window.
"""

import functools
import itertools
import pickle
from dataclasses import dataclass, field

import pytest

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.inputs_helpers import OVERHEAD
from maple.actions.movements_v2 import telecast, telecast_compiler
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 8765
IGN = "TestMage"
TELEPORT_KEY = "shift"
ULTIMATE_KEY = "d"
DIRECTIONS = ("left", "right", "up", "down")


@dataclass(frozen=True)
class _StubSkill:
    """A `Skill` whose key bind does not go through the keybindings config."""

    name: str
    key: str = field(repr=False)
    animation_time: float = field(default=0.0, repr=False)

    def key_bind(self, ign: str) -> str:
        return self.key


TELEPORT_SKILL = _StubSkill("Teleport", TELEPORT_KEY, 0.6)
ULTIMATE = _StubSkill("Genesis", ULTIMATE_KEY, 1.0)
# Long enough that truncation never hides a paired press, so the count and spacing of
# the rebuild can be read off the whole sequence.
UNTRUNCATED_ULTIMATE = _StubSkill("Genesis", ULTIMATE_KEY, 10.0)


_TELEPORT_PLAN = (
    _MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)

_WALK_PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 5),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)

_WALK_THEN_TELEPORT_PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 5),
    _MovementComponent(MovementTypes.TELEPORT_RIGHT, 3),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)


def _sequence(*steps: tuple[str, str], delay: float = 0.1) -> KeyboardInputWrapper:
    """A hand-built Input Sequence, compiled against nothing held."""
    return KeyboardInputWrapper(
        HANDLE,
        [key for key, _ in steps],
        [event for _, event in steps],
        [delay] * len(steps),
        initial_held_keys=frozenset(),
    )


def _steps(wrapper: KeyboardInputWrapper) -> list[tuple]:
    return list(zip(wrapper.keys, wrapper.events))


def _prefix_duration(wrapper: KeyboardInputWrapper, count: int) -> float:
    return sum(wrapper.delays[:count]) + OVERHEAD * count


def _tap_indices(wrapper: KeyboardInputWrapper) -> list[int]:
    """The Steps that press the teleport and the ultimate together."""
    return [
        idx
        for idx, (keys, events) in enumerate(_steps(wrapper))
        if keys == [TELEPORT_KEY, ULTIMATE_KEY] and events == ["keydown", "keydown"]
    ]


def _teleport_sequence() -> KeyboardInputWrapper:
    """Right-walking teleports, the shape `movements_v2.teleport` produces."""
    return _sequence(
        ("right", "keydown"),
        (TELEPORT_KEY, "keydown"),
        (TELEPORT_KEY, "keydown"),
        (TELEPORT_KEY, "keydown"),
        (TELEPORT_KEY, "keydown"),
    )


def _movement_compiler(movements, **kwargs) -> functools.partial:
    return functools.partial(
        compile_movements,
        movements=movements,
        handle=HANDLE,
        ign=IGN,
        speed=1.0,
        teleport=TELEPORT_SKILL,
        **kwargs,
    )


def _telecast(inner, initial_held_keys=frozenset()):
    return telecast_compiler(
        initial_held_keys,
        movement_compiler=inner,
        handle=HANDLE,
        ign=IGN,
        teleport_skill=TELEPORT_SKILL,
        ultimate_skill=ULTIMATE,
    )


def _compiler_for(result):
    """An inner compiler returning `result` and recording what it was handed."""
    seen = []

    def _compile(initial_held_keys):
        seen.append(initial_held_keys)
        return result

    return _compile, seen


# --- The rebuild ---------------------------------------------------------------


def test_a_teleport_region_becomes_paired_presses():
    """The whole point: the ultimate is cast on each blink, not after them."""
    fused = telecast(_teleport_sequence(), IGN, TELEPORT_SKILL, ULTIMATE)

    assert _tap_indices(fused)
    assert not any(keys == TELEPORT_KEY for keys, _ in _steps(fused))


def test_every_paired_press_is_released_by_a_paired_release():
    """
    The rebuild is re-press semantics, so each tap closes its own Hold. That is what
    makes the ultimate's release land inside the sequence rather than in the forced
    volley - strictly better for A4 Skill Key Closure.
    """
    fused = telecast(_teleport_sequence(), IGN, TELEPORT_SKILL, ULTIMATE)

    for idx in _tap_indices(fused):
        assert _steps(fused)[idx + 1] == (
            [TELEPORT_KEY, ULTIMATE_KEY],
            ["keyup", "keyup"],
        )


def test_non_teleport_steps_are_left_alone():
    fused = telecast(_teleport_sequence(), IGN, TELEPORT_SKILL, ULTIMATE)

    assert _steps(fused)[0] == ("right", "keydown")


def test_an_explicit_teleport_release_is_absorbed_into_the_tap():
    """
    A region absorbs a keyup sitting against its keydowns - the shape `teleport`
    builds when handed a `repeat_key`. The rebuild presses and releases the key
    itself, so leaving the original release behind would be a phantom one (A6).
    """
    sequence = _sequence(
        (TELEPORT_KEY, "keydown"),
        (TELEPORT_KEY, "keyup"),
    )

    fused = telecast(sequence, IGN, TELEPORT_SKILL, ULTIMATE)

    assert _steps(fused) == [
        ([TELEPORT_KEY, ULTIMATE_KEY], ["keydown", "keydown"]),
        ([TELEPORT_KEY, ULTIMATE_KEY], ["keyup", "keyup"]),
    ]


def test_the_rebuild_releases_nothing_it_did_not_press():
    """A6 No Phantom Release, over the rebuilt sequence."""
    fused = telecast(
        _movement_compiler(_TELEPORT_PLAN)(frozenset()),
        IGN,
        TELEPORT_SKILL,
        UNTRUNCATED_ULTIMATE,
    )

    down = set()
    for keys, events in _steps(fused):
        pairs = zip(keys, events) if isinstance(keys, list) else [(keys, events)]
        for key, event in pairs:
            if event == "keyup":
                assert key in down
                down.discard(key)
            else:
                down.add(key)


def test_the_ultimate_key_is_declared_for_forced_release():
    """
    A2 Terminal Release and D1 Cancel Safety. Every tap now releases the key it
    pressed, so the declaration is no longer the only thing that gets it back up -
    but a truncation landing between a tap's down and its up still leaves it held,
    and the forced volley only fires for keys the Held-Keys Ledger reports down.
    """
    fused = telecast(_teleport_sequence(), IGN, TELEPORT_SKILL, ULTIMATE)

    assert ULTIMATE_KEY in fused.forced_key_releases


def test_the_ultimate_key_is_declared_once():
    sequence = _teleport_sequence()
    sequence.forced_key_releases.append(ULTIMATE_KEY)

    fused = telecast(sequence, IGN, TELEPORT_SKILL, ULTIMATE)

    assert fused.forced_key_releases.count(ULTIMATE_KEY) == 1


def test_the_fused_sequence_is_truncated_to_the_ultimate_animation_time():
    """
    The shortest prefix that reaches the animation time. Past it the cast is over, so
    the rest of the movement belongs to whatever the bot decides next.
    """
    sequence = _sequence(*[(TELEPORT_KEY, "keydown")] * 40, delay=0.1)

    fused = telecast(sequence, IGN, TELEPORT_SKILL, ULTIMATE)

    assert len(fused.keys) < 40
    assert fused.duration >= ULTIMATE.animation_time
    assert _prefix_duration(fused, len(fused.keys) - 1) < ULTIMATE.animation_time


# --- Cadence -------------------------------------------------------------------


def test_a_three_teleport_plan_presses_the_pair_three_times():
    """
    The defect this rebuild fixes. The teleport keydowns a component compiles to are
    a `fill` at the input cadence - faithful for a *held* teleport key, but nothing a
    human does presses a *second* key thirty times a second. One press per teleport
    animation instead, which is also exactly `num_times` presses because `teleport`
    budgets `animation_time * num_times`.
    """
    sequence = _movement_compiler(_TELEPORT_PLAN)(frozenset())
    assert sum(1 for keys in sequence.keys if keys == TELEPORT_KEY) > 20

    fused = telecast(sequence, IGN, TELEPORT_SKILL, UNTRUNCATED_ULTIMATE)

    assert len(_tap_indices(fused)) == 3


def test_the_pair_is_re_pressed_once_per_teleport_animation():
    """Spacing is the teleport's own `animation_time`, not the input cadence."""
    fused = telecast(
        _movement_compiler(_TELEPORT_PLAN)(frozenset()),
        IGN,
        TELEPORT_SKILL,
        UNTRUNCATED_ULTIMATE,
    )

    starts = [_prefix_duration(fused, idx) for idx in _tap_indices(fused)]
    spacings = [later - earlier for earlier, later in itertools.pairwise(starts)]

    assert spacings
    assert all(
        spacing == pytest.approx(TELEPORT_SKILL.animation_time, abs=1e-6)
        for spacing in spacings
    )


def test_the_gap_between_taps_is_a_single_delay_step():
    """
    Settled by Spy++: auto-repeat does not come back to a key still held once another
    press has happened. So the gap carries no fill - one would fabricate a repeat run
    the game never sees from a human - and the Step before each re-press is simply the
    previous tap's release.
    """
    fused = telecast(
        _movement_compiler(_TELEPORT_PLAN)(frozenset()),
        IGN,
        TELEPORT_SKILL,
        UNTRUNCATED_ULTIMATE,
    )

    for idx in _tap_indices(fused)[1:]:
        assert _steps(fused)[idx - 1] == (
            [TELEPORT_KEY, ULTIMATE_KEY],
            ["keyup", "keyup"],
        )


def test_the_direction_key_stays_down_across_the_gaps():
    """Only its *repeating* is gone; the character keeps walking into the blinks."""
    fused = telecast(
        _movement_compiler(_TELEPORT_PLAN)(frozenset()),
        IGN,
        TELEPORT_SKILL,
        UNTRUNCATED_ULTIMATE,
    )

    last_tap = _tap_indices(fused)[-1]
    held = KeyboardInputWrapper.get_held_movement_keys(
        fused.keys[: last_tap + 1], fused.events[: last_tap + 1]
    )

    assert "right" in held


def test_the_rebuild_spends_the_regions_own_duration():
    """
    The budget is the compiled region's own duration, so the rebuild needs nothing the
    Input Sequence does not already carry - and the sequence it replaces keeps its
    length, which is what keeps the plan's distance intent intact.
    """
    sequence = _movement_compiler(_TELEPORT_PLAN)(frozenset())
    before = sequence.duration

    fused = telecast(sequence, IGN, TELEPORT_SKILL, UNTRUNCATED_ULTIMATE)

    assert fused.duration == pytest.approx(before, abs=1e-6)


# --- The compiler wrapper ------------------------------------------------------


def test_the_wrapper_fuses_a_sequence_that_teleports():
    inner, _ = _compiler_for(_teleport_sequence())

    result = _telecast(inner)

    assert [TELEPORT_KEY, ULTIMATE_KEY] in result.keys


def test_the_wrapper_falls_back_to_a_plain_cast_without_a_teleport():
    """
    Reachable even off a Movement Plan full of teleports: `total_duration` can cut the
    compile short of the first teleport component. The fallback still hits the mobs.
    """
    inner, _ = _compiler_for(_sequence(("right", "keydown"), ("right", "keyup")))

    result = _telecast(inner)

    assert all(keys != [TELEPORT_KEY, ULTIMATE_KEY] for keys in result.keys)
    assert ULTIMATE_KEY in result.forced_key_releases
    assert any(keys == ULTIMATE_KEY for keys in result.keys)


def test_the_wrapper_falls_back_when_the_plan_compiles_to_nothing():
    inner, _ = _compiler_for(None)

    result = _telecast(inner)

    assert result is not None
    assert any(keys == ULTIMATE_KEY for keys in result.keys)


def test_the_wrapper_logs_the_fallback(caplog):
    inner, _ = _compiler_for(None)

    with caplog.at_level("INFO"):
        _telecast(inner)

    assert any("No telecast possible" in record.message for record in caplog.records)


def test_the_wrapper_hands_the_held_keys_to_the_inner_compiler():
    """
    The seam's whole contract: held keys read from the ledger at dispatch have to
    reach the compile that shapes the sequence around them.
    """
    inner, seen = _compiler_for(_teleport_sequence())

    _telecast(inner, initial_held_keys=frozenset({"left"}))

    assert seen == [frozenset({"left"})]


def test_the_fallback_cast_sees_the_same_held_keys():
    """`left` is down and the cast presses nothing opposing it, so nothing is released."""
    inner, _ = _compiler_for(None)

    result = _telecast(inner, initial_held_keys=frozenset({"left"}))

    assert all(event != "keyup" for event in result.events)


def test_the_compiler_partial_is_picklable():
    """It travels to Main Process inside an ActionRequest, so it has to pickle."""
    compiler = functools.partial(
        telecast_compiler,
        movement_compiler=_movement_compiler(_TELEPORT_PLAN),
        handle=HANDLE,
        ign=IGN,
        teleport_skill=TELEPORT_SKILL,
        ultimate_skill=ULTIMATE,
    )

    assert pickle.loads(pickle.dumps(compiler)) is not None


# --- Over a real Movement Plan -------------------------------------------------


def test_a_plan_holding_a_teleport_compiles_to_the_teleport_key():
    """
    The equivalence the plan-level decision rests on. `TelecastMobsHitting` used to
    ask whether the compiled Input Sequence carried the teleport key; it now asks
    whether the Movement Plan holds a `TELEPORT_*` component. That substitution is
    only sound because the teleport key reaches a sequence through no other builder.
    """
    sequence = _movement_compiler(_TELEPORT_PLAN)(frozenset())

    assert any(keys == TELEPORT_KEY for keys in sequence.keys)


def test_a_plan_without_a_teleport_never_carries_the_teleport_key():
    sequence = _movement_compiler(_WALK_PLAN)(frozenset())

    assert all(keys != TELEPORT_KEY for keys in sequence.keys)


def test_a_plan_truncated_before_its_teleport_falls_back_to_a_plain_cast():
    """
    The plan-level check says telecast; the compile disagrees, because
    `total_duration` cuts it before the teleport component is ever built. This is the
    case the fallback exists for, and the reason the plan check being true in strictly
    more cases than the old compiled check is safe.
    """
    inner = _movement_compiler(_WALK_THEN_TELEPORT_PLAN, total_duration=1.0)

    result = _telecast(inner)

    assert all(keys != [TELEPORT_KEY, ULTIMATE_KEY] for keys in result.keys)
    assert any(keys == ULTIMATE_KEY for keys in result.keys)


def test_the_fused_plan_leaves_no_undeclared_skill_key_down_at_any_cancel_point():
    """
    D1 Cancel Safety, swept exhaustively over the fused sequence. Every tap releases
    both non-directional keys it pressed, so most cancel points now leave nothing
    latched at all - but a cut landing between a tap's down and its up still does, and
    there the invariant rests on `forced_key_releases`.
    """
    fused = _telecast(_movement_compiler(_TELEPORT_PLAN))

    declared = set(fused.forced_key_releases)
    for cancel_point in range(len(fused.keys) + 1):
        down = KeyboardInputWrapper.get_held_movement_keys(
            fused.keys[:cancel_point], fused.events[:cancel_point]
        )
        undeclared = {
            key for key in down - declared if key not in DIRECTIONS
        }
        assert not undeclared
