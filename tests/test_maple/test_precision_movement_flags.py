"""
Tests for issue #129: the two Movement Plan precision flags the precision-movement
taxonomy (`docs/planning/precision-movement-taxonomy.md`) names as PM2 and PM3, now
read off graph moves in virtual px (#396).

* **PM2, narrow landing** - a jump, drop or teleport landing on a platform at most
  `narrow_platform_threshold` virtual px wide (right end minus left end).
* **PM3, edge departure** - a sideways jump or teleport taking off within
  `edge_departure_threshold` virtual px of its platform's end, in the travel
  direction: the case where walking a tiny bit too far turns the gesture into a fall.

Both are plan-time properties of the move, so these tests hand
`MovementHandler.path_into_movements` a Path of one move over `narrow_perch`'s
platforms (`tests/test_maple/movement_lab/fixture_maps.py`): a 200 px floor from 0
to 200, a 30 px perch from 250 to 280, and another floor from 330 to 530.
"""

from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
)
from maple.model.navigation import Direction, Move, MoveKind, Path
from tests.test_maple.movement_lab import corpus

_ENTRY = next(entry for entry in corpus.FIXTURE_MAPS if entry.name == "narrow_perch")
_WORLD = corpus.world_map(_ENTRY)
_FLOOR, _PERCH, _FAR_FLOOR = _WORLD.platforms


def _component(handler: MovementHandler, move: Move) -> _MovementComponent:
    (component,) = handler.path_into_movements(Path((move,)))[:-1]
    return component


def _handler(**thresholds: float) -> MovementHandler:
    return MovementHandler(0, _WORLD, "T", **thresholds)  # type: ignore[arg-type]


def _jump_onto_the_perch(take_off: float = 200.0) -> Move:
    return Move(
        MoveKind.JUMP,
        Direction.RIGHT,
        (take_off, 0.0),
        (take_off + 55.0, 0.0),
        _FLOOR,
        _PERCH,
        0.55,
    )


def _teleport_onto_the_perch(take_off: float = 190.0) -> Move:
    return Move(
        MoveKind.TELEPORT,
        Direction.RIGHT,
        (take_off, 0.0),
        (265.0, 0.0),
        _FLOOR,
        _PERCH,
        0.74,
    )


def _jump_onto_the_far_floor() -> Move:
    return Move(
        MoveKind.JUMP,
        Direction.RIGHT,
        (280.0, 0.0),
        (340.0, 0.0),
        _PERCH,
        _FAR_FLOOR,
        0.55,
    )


# --- PM2: narrow ----------------------------------------------------------------


def test_the_fixture_has_the_widths_these_tests_rely_on() -> None:
    assert (_FLOOR.left, _FLOOR.right) == (0, 200)
    assert (_PERCH.left, _PERCH.right) == (250, 280)
    assert (_FAR_FLOOR.left, _FAR_FLOOR.right) == (330, 530)


def test_a_jump_onto_the_narrow_perch_is_flagged_narrow() -> None:
    component = _component(_handler(), _jump_onto_the_perch())

    assert component.movement_type is MovementTypes.JUMP_RIGHT
    assert component.narrow is True


def test_a_jump_onto_a_wide_platform_is_not_narrow() -> None:
    assert _component(_handler(), _jump_onto_the_far_floor()).narrow is False


def test_a_teleport_onto_the_narrow_perch_is_flagged_narrow() -> None:
    component = _component(_handler(), _teleport_onto_the_perch())

    assert component.movement_type is MovementTypes.TELEPORT_RIGHT
    assert component.narrow is True


def test_narrow_platform_threshold_governs_the_flag() -> None:
    """A threshold below the perch's 30 px width turns the same landing's `narrow` off."""
    handler = _handler(narrow_platform_threshold=29)

    assert _component(handler, _teleport_onto_the_perch()).narrow is False
    assert _component(handler, _jump_onto_the_perch()).narrow is False


# --- PM3: edge departure --------------------------------------------------------


def test_a_teleport_departing_near_the_platform_end_is_flagged_edge_departure() -> None:
    """Taking off at 190, 10 px from the floor's right end: inside the 80 px default."""
    assert _component(_handler(), _teleport_onto_the_perch()).edge_departure is True


def test_edge_departure_threshold_governs_how_close_counts() -> None:
    """
    The same take-off, read through a handler whose Knob is tighter than the gap: the
    flag follows the per-instance threshold, not a hardcoded distance.
    """
    handler = _handler(edge_departure_threshold=9)

    assert _component(handler, _teleport_onto_the_perch()).edge_departure is False


def test_a_jump_departing_from_the_platform_edge_is_flagged_edge_departure() -> None:
    """Taking off at the floor's right end exactly: edge departure under any threshold."""
    component = _component(_handler(edge_departure_threshold=0), _jump_onto_the_perch())

    assert component.edge_departure is True


def test_a_jump_departing_far_from_the_edge_is_not_an_edge_departure() -> None:
    assert (
        _component(_handler(), _jump_onto_the_perch(take_off=100.0)).edge_departure
        is False
    )


def test_the_defaults_are_the_old_five_minimap_px_in_virtual_px() -> None:
    """5 minimap px at 16 virtual px each (every MSCW minimap is `mag` 4)."""
    handler = _handler()

    assert handler.narrow_platform_threshold == 80
    assert handler.edge_departure_threshold == 80
