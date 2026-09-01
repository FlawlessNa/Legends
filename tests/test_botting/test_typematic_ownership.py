"""
Tests for typematic ownership: the Held-Keys Ledger carrying it, and the compiler seam
taking it (issue #109).

**A7 Typematic Legality** is decidable offline from `H0`, `T0` and the Steps, but `T0`
was never derivable from held keys alone - `{right}` is equally consistent with "right
was just pressed and owns typematic" and "right is a Continuation carry whose ownership
a teleport took and dropped". Ownership is cross-sequence state, and only the sole
sending process can observe it, so the ledger is where it lives: `record_step` already
witnesses every delivered Step, in order, at the moment it reaches the game.

The rule, as observed in Spy++ on a live client: a keydown claims ownership, a later
keydown takes it, and **any keyup ends repetition outright** rather than returning it to
a key still held.

Nothing here sends real input. The ledger is class-level state, reset around every test,
and every `KeyboardInputWrapper` is handed an explicit `initial_state`, so construction
never reads the ledger.
"""

from collections.abc import Iterator

import pytest

from botting.controller.inputs import held_keys_ledger
from botting.controller.inputs.focused_inputs import (
    KeyboardInputWrapper,
    get_input_state,
)
from botting.controller.inputs.held_keys_ledger import HeldKeysLedger, InputState
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementTypes,
    _MovementComponent,
    compile_movements,
)

HANDLE = 1234
IGN = "TestChar"

_WALK = (
    _MovementComponent(MovementTypes.WALK_RIGHT, 10),
    _MovementComponent(MovementTypes.END_OF_MOVEMENT, 0),
)


@pytest.fixture(autouse=True)
def reset_ledger() -> Iterator[None]:
    """The ledger is process-wide state, so every test starts and ends from empty."""
    HeldKeysLedger.reset()
    yield
    HeldKeysLedger.reset()


class _FakeClock:
    """Stands in for the `time` module inside the ledger, so elapsed is not a race."""

    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _FakeClock:
    fake = _FakeClock()
    monkeypatch.setattr(held_keys_ledger, "time", fake)
    return fake


def _a7_violations(wrapper: KeyboardInputWrapper) -> list[tuple[int, str]]:
    """
    **A7** verbatim, walked independently of the code under test: for every keydown of
    `k` at Step `i`, if `k` is in `down(i-1)` the Step is a repeat and requires
    `own(i-1) == k`; otherwise it is a press and sets `own(i) = k`.

    Decidable only because the sequence now carries all three of `H0`, `T0` and the
    Steps. Before #109 the second of those was missing and this function could not be
    written.
    """
    state = wrapper.initial_state or InputState()
    down = set(state.held_keys)
    own = state.typematic_owner
    violations: list[tuple[int, str]] = []
    for i, (keys, events) in enumerate(zip(wrapper.keys, wrapper.events)):
        pairs = list(zip(keys, events)) if isinstance(keys, list) else [(keys, events)]
        for key, event in pairs:
            if event == "keydown":
                if key in down and own != key:
                    violations.append((i, key))
                down.add(key)
                own = key
            elif event == "keyup":
                down.discard(key)
                own = None
    return violations


# --- the ledger observes ownership --------------------------------------------


def test_a_keydown_claims_ownership() -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    assert HeldKeysLedger.input_state(HANDLE).typematic_owner == "right"


def test_a_later_keydown_takes_ownership() -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")
    HeldKeysLedger.record_step(HANDLE, "shift", "keydown")

    state = HeldKeysLedger.input_state(HANDLE)
    assert state.held_keys == frozenset({"right", "shift"})
    assert state.typematic_owner == "shift"


def test_a_keyup_ends_ownership_rather_than_returning_it_to_a_held_key() -> None:
    """
    Load-bearing, and the whole reason `T0` cannot be derived from held keys: `right`
    is still down afterwards, but nothing repeats. This is the Continuation carry the
    teleport shape produces - `right` down, ownership gone.
    """
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")
    HeldKeysLedger.record_step(HANDLE, "shift", "keydown")
    HeldKeysLedger.record_step(HANDLE, "shift", "keyup")

    state = HeldKeysLedger.input_state(HANDLE)
    assert state.held_keys == frozenset({"right"})
    assert state.typematic_owner is None


def test_a_keyup_for_a_key_never_held_still_ends_ownership() -> None:
    """`release_all`'s straggler volley is exactly this shape."""
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    HeldKeysLedger.record_step(HANDLE, "up", "keyup")

    assert HeldKeysLedger.input_state(HANDLE).typematic_owner is None


def test_the_last_keydown_of_a_simultaneous_batch_owns() -> None:
    """One `SendInput` array, applied in Step order - the order the game sees."""
    HeldKeysLedger.record_step(HANDLE, ["up", "space"], ["keydown", "keydown"])

    assert HeldKeysLedger.input_state(HANDLE).typematic_owner == "space"


def test_a_keyup_inside_a_batch_ends_ownership_claimed_earlier_in_it() -> None:
    HeldKeysLedger.record_step(HANDLE, "left", "keydown")

    HeldKeysLedger.record_step(HANDLE, ["right", "left"], ["keydown", "keyup"])

    state = HeldKeysLedger.input_state(HANDLE)
    assert state.held_keys == frozenset({"right"})
    assert state.typematic_owner is None


def test_a_mouse_step_leaves_ownership_untouched() -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    HeldKeysLedger.record_step(HANDLE, None, None)

    assert HeldKeysLedger.input_state(HANDLE).typematic_owner == "right"


def test_ownership_is_per_handle() -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")
    HeldKeysLedger.record_step(5678, "left", "keydown")

    assert HeldKeysLedger.input_state(HANDLE).typematic_owner == "right"
    assert HeldKeysLedger.input_state(5678).typematic_owner == "left"


# --- unknown ownership collapses into "nobody owns" ---------------------------


def test_an_untouched_handle_owns_nothing() -> None:
    assert HeldKeysLedger.input_state(HANDLE) == InputState()


def test_clear_drops_ownership_with_the_entry() -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    HeldKeysLedger.clear(HANDLE)

    assert HeldKeysLedger.input_state(HANDLE) == InputState()


def test_reset_drops_ownership() -> None:
    """
    The session-start sweep's shape. `GetAsyncKeyState` can recover which keys are down
    and can never recover which one repeats, so the sweep leaves nobody owning - the
    representable default rather than a separately modelled "unknown".
    """
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")

    HeldKeysLedger.reset()

    assert HeldKeysLedger.input_state(HANDLE) == InputState()


# --- elapsed is stamped by the ledger, measured at the read -------------------


def test_elapsed_measures_from_the_owning_keydown(clock: _FakeClock) -> None:
    """
    A sequence that presses `right` in its final 100ms hands the next one an owner whose
    typematic delay is already 100ms spent.
    """
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")
    clock.now += 0.1

    assert HeldKeysLedger.input_state(HANDLE).owner_elapsed == pytest.approx(0.1)


def test_a_later_keydown_restarts_the_clock(clock: _FakeClock) -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")
    clock.now += 0.5
    HeldKeysLedger.record_step(HANDLE, "shift", "keydown")
    clock.now += 0.05

    state = HeldKeysLedger.input_state(HANDLE)
    assert state.typematic_owner == "shift"
    assert state.owner_elapsed == pytest.approx(0.05)


def test_elapsed_is_zero_when_nobody_owns(clock: _FakeClock) -> None:
    HeldKeysLedger.record_step(HANDLE, "right", "keydown")
    clock.now += 0.5
    HeldKeysLedger.record_step(HANDLE, "right", "keyup")

    assert HeldKeysLedger.input_state(HANDLE).owner_elapsed == 0.0


# --- the seam's read ----------------------------------------------------------


def test_the_seam_narrows_held_keys_but_not_the_owner() -> None:
    """
    `held_keys` is the movement-key set the seam has always described. The owner is not
    narrowed: `teleport`'s skill-key fill is legal precisely because that key owns, and
    collapsing a skill-key owner into "nobody" would forbid it.
    """
    HeldKeysLedger.record_step(HANDLE, ["right", "shift"], ["keydown", "keydown"])

    state = get_input_state(HANDLE)

    assert state.held_keys == frozenset({"right"})
    assert state.typematic_owner == "shift"


# --- the sequence carries T0 the way it carries H0 ----------------------------


def test_typematic_owner_is_seeded_from_the_start_state() -> None:
    """
    The `own(-1) = T0` half of what #97 fixed for `down(-1) = H0`. A sequence whose
    Steps touch nothing still inherits the owner, or the carry dies at the second
    builder in a Movement Plan.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE, initial_state=InputState(frozenset({"right"}), "right", 0.1)
    )

    assert wrapper.typematic_owner == "right"


def test_a_keydown_in_the_sequence_takes_ownership_from_the_inherited_key() -> None:
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["shift"],
        ["keydown"],
        [0.0],
        initial_state=InputState(frozenset({"right"}), "right", 0.1),
    )

    assert wrapper.typematic_owner == "shift"


def test_a_keyup_in_the_sequence_ends_inherited_ownership() -> None:
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["shift", "shift"],
        ["keydown", "keyup"],
        [0.0, 0.0],
        initial_state=InputState(frozenset({"right"}), "right", 0.1),
    )

    assert wrapper.keys_held == {"right"}
    assert wrapper.typematic_owner is None


def test_truncate_carries_the_start_state_so_the_prefix_owns_what_it_should() -> None:
    """
    Truncation is the normal case - rotation truncates every Action - and the Delivered
    Prefix is what the next sequence inherits, so its `T0` has to survive the copy.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["shift"],
        ["keydown"],
        [0.5],
        initial_state=InputState(frozenset({"right"}), "right", 0.1),
    )

    assert wrapper.truncate(0.0).typematic_owner == "right"


def test_the_walk_keeps_step_order_inside_a_batch() -> None:
    assert (
        KeyboardInputWrapper.get_typematic_owner(
            [["a", "b"]], [["keydown", "keydown"]], initial="right"
        )
        == "b"
    )


def test_the_walk_starts_from_nobody_owning_by_default() -> None:
    assert KeyboardInputWrapper.get_typematic_owner([], []) is None


def test_a_compiled_plan_carries_the_start_state_it_was_given() -> None:
    """
    The seam end to end: what `compile_and_send` reads from the ledger has to reach the
    compiled sequence, or **A7** is undecidable over the thing the lab actually checks.
    """
    state = InputState(frozenset({"right"}), "right", 0.1)

    wrapper = compile_movements(
        state, movements=_WALK, handle=HANDLE, ign=IGN, speed=10.0
    )

    assert wrapper is not None
    assert wrapper.initial_state == state


# --- A7 is now decidable ------------------------------------------------------


def test_a_repeat_of_the_owning_key_is_legal() -> None:
    """
    The Continuation carry where `right` was genuinely the last key pressed: repeating
    it is exactly what a human's held key produces.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "right"],
        ["keydown", "keydown"],
        [0.5, 0.03],
        initial_state=InputState(frozenset({"right"}), "right", 0.1),
    )

    assert _a7_violations(wrapper) == []


def test_the_same_steps_are_illegal_when_the_carry_owns_nothing() -> None:
    """
    Load-bearing. Identical `H0`, identical Steps, opposite verdicts - decided solely by
    `T0`. This is the teleport shape: `right` is still down, but a teleport took
    ownership and its keyup dropped it, so no repeat is producible. Without ownership
    carried into compilation both cases look the same and A7 cannot be checked at all.

    Only Step 0 is flagged: A7's keydown clause *sets* `own(i) = k`, so the illegal
    repeat claims ownership and every Step after it is a legal repeat. That is the
    catalogue's "a fill is legal exactly when its own first Step is a genuine press",
    read off the invariant rather than restated beside it.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "right"],
        ["keydown", "keydown"],
        [0.5, 0.03],
        initial_state=InputState(frozenset({"right"}), None, 0.0),
    )

    assert _a7_violations(wrapper) == [(0, "right")]


def test_a_fill_whose_own_first_step_is_a_press_is_legal() -> None:
    """`move` on a fresh direction: the press claims ownership, the repeats follow it."""
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "right", "right"],
        ["keydown", "keydown", "keydown"],
        [0.5, 0.03, 0.03],
        initial_state=InputState(),
    )

    assert _a7_violations(wrapper) == []


def test_a_fill_resumed_after_another_keys_keyup_is_illegal() -> None:
    """
    `teleport`'s `repeat_key` branch, in miniature: direction down, skill down, skill
    up, then a fill. The skill's keyup ended repetition outright, so every filled Step
    afterwards is a keydown no human produces.
    """
    wrapper = KeyboardInputWrapper(
        HANDLE,
        ["right", "shift", "shift", "right"],
        ["keydown", "keydown", "keyup", "keydown"],
        [0.5, 0.05, 0.05, 0.03],
        initial_state=InputState(),
    )

    assert _a7_violations(wrapper) == [(3, "right")]
