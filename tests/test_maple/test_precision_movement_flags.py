"""
Tests for issue #129: the two Movement Plan model gaps the precision-movement
taxonomy (`docs/planning/precision-movement-taxonomy.md`) names as PM2 and PM3.

* **PM2, teleport half** - `narrow` was only ever set for `JUMP_*` components. A
  `TELEPORT_*` landing on a platform at or below `narrow_platform_threshold` got no
  flag, so a narrow teleport landing was indistinguishable from an open one.
* **PM3, edge departure** - no flag existed for a `JUMP_*`/`TELEPORT_*` whose start
  node sits within `edge_departure_threshold` minimap px of its platform's end, in
  the travel direction - the case where walking a tiny bit too far turns the gesture
  into a fall.

Both are plan-time properties, read off `_path_into_movements_uncached`'s connection
handling, so these tests exercise `MovementHandler.path_into_movements` directly over
a real grid rather than compiling anything.

`narrow_perch` is reused rather than a new fixture: its floor-to-perch gap already
carries real `JUMP_RIGHT` and (teleport-enabled) `TELEPORT_RIGHT` connections at
several departure points, which is exactly the geometry PM2 and PM3 need - see
`tests/test_maple/movement_lab/corpus.py`.
"""

from maple.model.mechanics.maple_map import MapleMinimap
from maple.model.mechanics.minimap_creation.minimap_grid import MinimapGrid
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
)
from tests.test_maple.movement_lab import corpus

_ENTRY = next(entry for entry in corpus.FIXTURE_MAPS if entry.name == "narrow_perch")


def _minimap() -> MapleMinimap:
    return corpus.minimap(_ENTRY)


def _grid(allow_teleport: bool) -> MinimapGrid:
    """Built fresh (not `corpus.grid`, which is pinned to the entry's own frozen
    configuration - `narrow_perch` is frozen with teleport off)."""
    return _minimap().generate_grid(allow_teleport, 1.0, 1.0)


def _plan(
    handler: MovementHandler,
    grid: MinimapGrid,
    start: tuple[int, int],
    end: tuple[int, int],
) -> tuple[_MovementComponent, ...]:
    path = (grid.node(*start), grid.node(*end))
    return handler.path_into_movements(path, grid)


# --- PM2: narrow now applies to teleport landings, not only jumps -----------------


def test_a_jump_onto_the_narrow_perch_is_flagged_narrow() -> None:
    """Sanity check: the pre-existing jump half still holds after the refactor that
    generalized `_JUMP_CONNECTION_TYPES` into `_NARROW_CONNECTION_TYPES`."""
    grid = _grid(allow_teleport=False)
    handler = MovementHandler(0, _minimap(), "T")
    (component,) = _plan(handler, grid, (14, 15), (18, 13))[:-1]

    assert component.movement_type is MovementTypes.JUMP_RIGHT
    assert component.narrow is True


def test_a_teleport_onto_the_narrow_perch_is_now_flagged_narrow() -> None:
    """The model gap this ticket closes: before #129, this component's `narrow` was
    always `False`, regardless of the perch's 3px width."""
    grid = _grid(allow_teleport=True)
    handler = MovementHandler(0, _minimap(), "T")
    (component,) = _plan(handler, grid, (12, 15), (21, 13))[:-1]

    assert component.movement_type is MovementTypes.TELEPORT_RIGHT
    assert component.narrow is True


def test_narrow_platform_threshold_still_governs_the_teleport_half() -> None:
    """The Knob shape is shared: a threshold below the perch's 3px width turns the
    same teleport's `narrow` off, exactly as it already does for jumps."""
    grid = _grid(allow_teleport=True)
    handler = MovementHandler(0, _minimap(), "T", narrow_platform_threshold=1)
    (component,) = _plan(handler, grid, (12, 15), (21, 13))[:-1]

    assert component.narrow is False


# --- PM3: edge departure --------------------------------------------------------


def test_a_teleport_departing_near_the_platform_end_is_flagged_edge_departure() -> None:
    """Start node (12, 15) sits 2px from `floor`'s right end (14) - inside the 5px
    default. Before #129, no flag existed to express this at all."""
    grid = _grid(allow_teleport=True)
    handler = MovementHandler(0, _minimap(), "T")
    (component,) = _plan(handler, grid, (12, 15), (21, 13))[:-1]

    assert component.edge_departure is True


def test_edge_departure_threshold_governs_how_close_counts() -> None:
    """
    Same real connection (departure 2px from the platform end) as the test above,
    read through a handler whose Knob is tighter than the gap: the flag must follow
    the per-instance threshold, not a hardcoded distance.
    """
    grid = _grid(allow_teleport=True)
    handler = MovementHandler(0, _minimap(), "T", edge_departure_threshold=1)
    (component,) = _plan(handler, grid, (12, 15), (21, 13))[:-1]

    assert component.edge_departure is False


def test_a_jump_departing_from_the_platform_edge_is_flagged_edge_departure() -> None:
    """The jump half: departure node (14, 15) is exactly `floor`'s right end (0px
    away), so it is edge-departure under any positive threshold."""
    grid = _grid(allow_teleport=False)
    handler = MovementHandler(0, _minimap(), "T")
    (component,) = _plan(handler, grid, (14, 15), (18, 13))[:-1]

    assert component.movement_type is MovementTypes.JUMP_RIGHT
    assert component.edge_departure is True
