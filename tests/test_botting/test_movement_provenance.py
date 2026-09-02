"""
Tests for Provenance - the record of which Movement Plan component produced each
Step (issue #102).

**B1 Truncation Integrity** says the cut never lands inside a `JUMP*`, `TELEPORT*` or
`ENTER_PORTAL` component. It was unenforceable: a Step carried no record of the
component it came from, the compiler knew the boundary and discarded it, and given only
a truncated Input Sequence a jump that was *cut* is indistinguishable from a jump whose
keyup was trimmed. `KeyboardInputWrapper.origins` carries that record, one component
index per Step, written by `compile_movements` as it walks the plan.

Three things are pinned here, in order:

1. **Shape.** `len(origins) == len(keys)` through construction, `append`, `insert` and
   `truncate`. Provenance that has drifted out of step with the Steps is worse than
   none - it names the wrong Step and reads as if it were right.
2. **Boundaries.** Each component owns a contiguous run of Steps, and the numbering is
   anchored to something visible in the sequence rather than to itself.
3. **B1 is checkable.** A plan cut mid-jump is *detected* by a check written against
   `origins`, and the same check stays quiet on a cut through a walk.

Whether B1 then *holds* is a separate question, and today it does not: `truncate` cuts
on elapsed time alone. `test_a_cut_inside_the_jump_component_is_detected` asserts the
detection, not the defect - if `truncate` is later taught to back off to the last
complete atomic component, that test is the one to rewrite, and the negative control
below it is what proves the check discriminates in the meantime.

Nothing here sends real input: every wrapper is built with an explicit `initial_state`,
so construction never reads the Held-Keys Ledger, and `key_binds` is stubbed because
`configs/keybindings.ini` is a personal config that no checkout is guaranteed to have.
"""

from collections import Counter
from itertools import groupby

import pytest

from botting.controller.inputs.focused_inputs import (
    NO_COMPONENT,
    KeyboardInputWrapper,
)
from botting.controller.inputs.held_keys_ledger import InputState
from maple.model.mechanics import movement_mechanics_v2
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 1234
IGN = "TestChar"
JUMP_KEY = "space"
SPEED = 10.0
NOBODY = InputState(frozenset())

# The components B1 calls atomic: an in-game gesture a cut splits rather than shortens.
ATOMIC = frozenset(
    {
        MovementTypes.JUMP,
        MovementTypes.JUMP_LEFT,
        MovementTypes.JUMP_RIGHT,
        MovementTypes.JUMP_DOWN,
        MovementTypes.ENTER_PORTAL,
        MovementTypes.TELEPORT_LEFT,
        MovementTypes.TELEPORT_RIGHT,
        MovementTypes.TELEPORT_UP,
        MovementTypes.TELEPORT_DOWN,
    }
)

# walk, jump, walk, then the sentinel `pairwise` needs in order to see the last real
# component as an `upcoming_move`. The walk runs ~2.0s, the jump ~1.6s and the second
# walk ~1.0s at `SPEED`, which is what makes the cut points below land where they say.
PLAN = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 20),
    _MovementComponent(MovementTypes.JUMP_RIGHT, 2),
    _MovementComponent(MovementTypes.WALK_RIGHT, 10),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)
WALK, JUMP, LAST_WALK = 0, 1, 2

# Well inside the jump and well inside the first walk respectively, with room to spare
# for the +/-5% jitter on every delay.
CUT_INSIDE_THE_JUMP = 2.5
CUT_INSIDE_THE_WALK = 1.0


@pytest.fixture(autouse=True)
def jump_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Stubs the key bind lookup, which reads a gitignored personal config.

    `compile_movements` resolves the jump key itself, so a plan holding a `JUMP*`
    component cannot be compiled at all without this - which is why the rest of the
    suite only ever puts a jump in the *upcoming* slot.
    """
    monkeypatch.setattr(
        movement_mechanics_v2, "key_binds", lambda ign: {"jump": JUMP_KEY}
    )


def _compile(total_duration: float | None = None) -> KeyboardInputWrapper:
    """`PLAN` compiled over the module's fixed handle/ign/speed, minus the `None`."""
    wrapper = compile_movements(
        NOBODY,
        movements=PLAN,
        handle=HANDLE,
        ign=IGN,
        speed=SPEED,
        total_duration=total_duration,
    )
    assert wrapper is not None
    return wrapper


def _runs(wrapper: KeyboardInputWrapper) -> list[tuple[int, int]]:
    """The sequence's Provenance run-length collapsed, as `(origin, length)` pairs."""
    return [(origin, len(list(group))) for origin, group in groupby(wrapper.origins)]


def _steps_carrying(wrapper: KeyboardInputWrapper, key: str) -> set[int]:
    """The components that produced a Step carrying `key`, in any position."""
    return {
        origin
        for step, origin in zip(wrapper.keys, wrapper.origins)
        if key in (step if isinstance(step, list) else [step])
    }


def _b1_violation(full: KeyboardInputWrapper, cut: KeyboardInputWrapper) -> int | None:
    """
    **B1 Truncation Integrity** as an actual check: the atomic component the cut landed
    inside, or `None` when the cut fell on a boundary.

    A component is split when the truncated sequence holds fewer of its Steps than the
    untruncated compile of the same plan did. That comparison is only expressible
    because both sequences carry Provenance - the whole point of this ticket. Walks are
    excluded by B1's own statement: shortening a walk shortens a distance, it does not
    cut a gesture in half, so a walk's Step count legitimately differs run to run with
    the delay jitter.
    """
    before = Counter(origin for origin in full.origins if origin != NO_COMPONENT)
    after = Counter(origin for origin in cut.origins if origin != NO_COMPONENT)
    for origin, kept in sorted(after.items()):
        if kept < before[origin] and PLAN[origin].movement_type in ATOMIC:
            return origin
    return None


# --- 1. shape ---------------------------------------------------------------------


def test_construction_pads_provenance_for_the_steps_handed_in() -> None:
    """
    A wrapper built from raw Steps satisfies the invariant without being handed an
    `origins`. That is what keeps the field optional: everything outside
    `compile_movements` - `cast_skill`, the toolkit, this suite - carries Provenance it
    never asked for and never has to maintain.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "up"],
        ["keydown", "keydown"],
        [0.1, 0.1],
        initial_state=NOBODY,
    )

    assert wrapper.origins == [NO_COMPONENT, NO_COMPONENT]
    assert len(wrapper.origins) == len(wrapper.keys)


def test_construction_stamps_the_steps_handed_in_with_the_cursor() -> None:
    """
    The padding takes the cursor's value, not the sentinel's. The first component's
    builder *constructs* the wrapper rather than appending to one, so this is the only
    door its Steps can come through.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right"],
        ["keydown"],
        [0.1],
        initial_state=NOBODY,
        current_origin=7,
    )

    assert wrapper.origins == [7]


def test_the_opposite_key_release_inserted_at_construction_carries_provenance() -> None:
    """
    `__post_init__` can splice a release in ahead of the Steps it was handed. It goes in
    at index 0, so Provenance has to go in at index 0 too - appending it would name the
    release's origin against the *last* Step instead.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right"],
        ["keydown"],
        [0.1],
        initial_state=InputState(frozenset({"left"})),
    )

    assert wrapper.keys[0] == ["left"]
    assert len(wrapper.origins) == len(wrapper.keys)


def test_append_stamps_the_step_with_the_cursor() -> None:
    wrapper = KeyboardInputWrapper(HANDLE, initial_state=NOBODY)
    wrapper.current_origin = 3
    wrapper.append("right", "keydown", 0.1)
    wrapper.current_origin = 4
    wrapper.append("right", "keyup", 0.1)

    assert wrapper.origins == [3, 4]


def test_insert_splices_provenance_at_the_same_index() -> None:
    """
    The silently-shifted index B1 cannot survive. `move` inserts its release at the
    index its own build started from, so an `origins` that only ever grew at the tail
    would leave every entry after the splice naming the Step before it.
    """
    wrapper = KeyboardInputWrapper(HANDLE, initial_state=NOBODY)
    wrapper.current_origin = 0
    wrapper.append("right", "keydown", 0.1)
    wrapper.current_origin = 1
    wrapper.append("up", "keydown", 0.1)
    # Three distinct origins, so the spliced entry cannot land in the right place by
    # coincidence: appending it instead would read `[0, 1, 2]`, which is a perfectly
    # plausible-looking Provenance for the wrong sequence of Steps.
    wrapper.current_origin = 2
    wrapper.insert(1, "down", "keyup", 0.1)

    assert wrapper.keys == ["right", "down", "up"]
    assert wrapper.origins == [0, 2, 1]


def test_truncate_carries_each_steps_own_provenance() -> None:
    """
    The copy answers "which component was this Step in" exactly as the original did.
    Anything else and the cut cannot be located against a component boundary, which is
    the only reason Provenance exists.
    """
    full = _compile()
    cut = full.truncate(CUT_INSIDE_THE_JUMP)

    assert len(cut.origins) == len(cut.keys)
    assert cut.origins == full.origins[: len(cut.keys)]


@pytest.mark.parametrize(
    "total_duration", [None, CUT_INSIDE_THE_JUMP, CUT_INSIDE_THE_WALK]
)
def test_a_compiled_sequence_carries_one_origin_per_step(
    total_duration: float | None,
) -> None:
    """A1 Shape, extended to the fourth list. Truncated or not, they stay in step."""
    wrapper = _compile(total_duration)

    assert len(wrapper.origins) == len(wrapper.keys)
    assert len(wrapper.origins) == len(wrapper.events)
    assert len(wrapper.origins) == len(wrapper.delays)


# --- 2. boundaries ----------------------------------------------------------------


def test_each_component_owns_one_contiguous_run_of_steps() -> None:
    """
    The plan's components appear in `origins` in plan order, once each, with no run
    repeating - so the first and the last Step of every component both name that
    component, and the boundary between two components is a single index.

    The run *lengths* are deliberately not asserted: a walk's Step count moves with the
    delay jitter, and pinning it here would make this a golden rather than a check on
    Provenance. `test_goldens.py` (issue #104) is where lengths belong.
    """
    assert [origin for origin, _ in _runs(_compile())] == [
        WALK,
        JUMP,
        LAST_WALK,
        NO_COMPONENT,
    ]


def test_the_jump_key_is_pressed_only_by_the_jump_component() -> None:
    """
    Anchors the numbering to the sequence instead of to itself. Contiguous runs
    numbered 0, 1, 2 would look right even if the compiler were off by one; the jump key
    is emitted by exactly one builder, so finding it under component 1 - and nowhere
    else - is what says the indices name the components a reader means.
    """
    assert _steps_carrying(_compile(), JUMP_KEY) == {JUMP}


def test_the_terminal_release_belongs_to_no_component() -> None:
    """
    The `for...else` release closes the sequence rather than a gesture. Inheriting the
    last component's index would make it look like part of that component, and B1 would
    then read a plan's final component as one Step longer than its builder emitted.
    """
    wrapper = _compile()

    assert wrapper.origins[-1] == NO_COMPONENT
    assert wrapper.events[-1] == ["keyup"]


def test_the_precision_pre_stop_belongs_to_no_component() -> None:
    """
    Same question on the truncated path. The pre-stop is appended to the copy
    `truncate` returns, so the copy's cursor is what decides - and a copy whose cursor
    still named the last Step copied would hand this release the walk's index.
    """
    wrapper = _compile(CUT_INSIDE_THE_WALK)

    assert wrapper.keys[-1] == "right"
    assert wrapper.events[-1] == "keyup"
    assert wrapper.origins[-1] == NO_COMPONENT


# --- 3. B1 becomes checkable ------------------------------------------------------


def test_a_cut_inside_the_jump_component_is_detected() -> None:
    """
    The ticket's acceptance: B1 is checkable. `CUT_INSIDE_THE_JUMP` lands between the
    jump's first Step and its last, and the check names the jump.

    This asserts the *detection*, not the defect. B1 does not hold today - `truncate`
    cuts on elapsed time alone - and fixing that is its own ticket. When it is fixed,
    this test inverts: the cut backs off to the walk's end and `_b1_violation` returns
    `None`.
    """
    full = _compile()

    assert _b1_violation(full, full.truncate(CUT_INSIDE_THE_JUMP)) == JUMP


def test_a_cut_inside_a_walk_is_not_a_violation() -> None:
    """
    The negative control, and the reason the check above means anything: a check that
    fired on every truncation would be no check at all. Shortening a walk shortens a
    distance; B1 is only about the gestures a cut splits.
    """
    full = _compile()

    assert _b1_violation(full, full.truncate(CUT_INSIDE_THE_WALK)) is None
