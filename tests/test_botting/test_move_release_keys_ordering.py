"""
Tests for **A6 No Phantom Release** and **A7 Typematic Legality**
(`docs/planning/movement-invariant-catalogue.md`), for the race issue #132 named:
`move`'s explicit `release_keys` argument and `_clear_opposites` (triggered by the
`first_keys` press it inserts) can both fire on the same key.

`move` captured `release_index` before pressing `first_keys`, then inserted
`release_keys`'s release at that now-stale index. When `secondary_direction`'s
opposite was already held, `_clear_opposites` released it once as a side effect of
the press, and the explicit `release_keys` block released it *again* - and because
the press had already grown `structure.keys` past `release_index`, the real press
landed sandwiched between the two duplicate releases. `needs_press`'s all-or-nothing
batching compounded it: `direction`, already held and not what needed pressing, was
re-pressed anyway because `secondary_direction` wasn't held yet.

Nothing here sends real input: the sequence is compiled against an explicit
`initial_state`, and the handle refers to no real window.
"""

from collections.abc import Iterator
from typing import Any

from botting.controller.inputs.focused_inputs import KeyboardInputWrapper
from botting.controller.inputs.held_keys_ledger import InputState
from maple.actions import movements_v2

HANDLE = 1234


def _steps(wrapper: KeyboardInputWrapper) -> Iterator[tuple[str, Any]]:
    """Yields one `(key, event)` pair per key in each Step, in Step order."""
    for keys, events in zip(wrapper.keys, wrapper.events):
        if isinstance(keys, list):
            yield from zip(keys, events)
        else:
            yield keys, events


def _walk(
    wrapper: KeyboardInputWrapper,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Replays the Steps, returning `(phantom_releases, illegal_repeats)`."""
    down: set[str] = set(
        wrapper.initial_state.held_keys if wrapper.initial_state else ()
    )
    owner = wrapper.initial_state.typematic_owner if wrapper.initial_state else None
    phantom_releases: list[tuple[str, str]] = []
    illegal_repeats: list[tuple[str, str]] = []
    for key, event in _steps(wrapper):
        if event == "keydown":
            if key in down and owner != key:
                illegal_repeats.append((key, event))
            down.add(key)
            owner = key
        elif event == "keyup":
            if key not in down:
                phantom_releases.append((key, event))
            down.discard(key)
            if owner == key:
                owner = None
    return phantom_releases, illegal_repeats


def _base_structure(
    held_keys: frozenset[str], typematic_owner: str | None
) -> KeyboardInputWrapper:
    """A structure with no Steps of its own, seeded to look like mid-plan state."""
    return KeyboardInputWrapper(
        HANDLE,
        initial_state=InputState(held_keys, typematic_owner),
    )


# --- The ticket's own repro: WALK_LEFT into a component with secondary="up" --------


def test_release_keys_does_not_duplicate_clear_opposites_release() -> None:
    """
    `left` and `down` are both held entering a `move` call with `secondary="up"`,
    `release_keys="down"` - `compile_movements`' shape for a `WALK_LEFT` heading into
    `ENTER_PORTAL`/`CLIMB_UP`. `down` must be released exactly once.
    """
    structure = _base_structure(frozenset({"left", "down"}), typematic_owner="left")

    structure = movements_v2.move(
        HANDLE,
        "left",
        "up",
        duration=0.5,
        structure=structure,
        release_keys="down",
    )

    down_releases = [
        (key, event)
        for key, event in _steps(structure)
        if key == "down" and event == "keyup"
    ]
    assert len(down_releases) == 1


def test_release_keys_does_not_produce_a_phantom_release() -> None:
    """A6: no keyup targets a key that is not down at that point in the sequence."""
    structure = _base_structure(frozenset({"left", "down"}), typematic_owner="left")

    structure = movements_v2.move(
        HANDLE,
        "left",
        "up",
        duration=0.5,
        structure=structure,
        release_keys="down",
    )

    phantom_releases, _ = _walk(structure)
    assert not phantom_releases


def test_already_held_direction_is_not_re_pressed() -> None:
    """
    A7: `left` already owns typematic entering the call, so the Step that presses
    `up` must not bundle an illegal repeat of `left` alongside it.
    """
    structure = _base_structure(frozenset({"left", "down"}), typematic_owner="left")

    structure = movements_v2.move(
        HANDLE,
        "left",
        "up",
        duration=0.5,
        structure=structure,
        release_keys="down",
    )

    _, illegal_repeats = _walk(structure)
    assert not illegal_repeats
    left_presses = [
        (key, event)
        for key, event in _steps(structure)
        if key == "left" and event == "keydown"
    ]
    assert not left_presses
