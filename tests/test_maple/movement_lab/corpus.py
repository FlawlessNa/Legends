"""
The Corpus the movement lab compiles against: the maps, and the frozen sample of
start-and-end pairs per map.

Two tiers, per issue #10. **Fixture maps** are written by hand under `maps/`, each
built to force one movement type, and they carry the coverage matrix — so coverage
never depends on whether a real map happens to contain a jump-down. **Real mapfiles**
come from `configs/maps/` and carry realism.

The sample is *frozen*: `pairs/<map>.json` is generated once from a fixed seed and
checked in, with each pair's reachability recorded as **data**. Nothing here queries
reachability at runtime, so a pair that stops being reachable fails a check instead of
being silently skipped. Regenerate with `python toolkit/generate_movement_lab_pairs.py`.

Every map fixes **one** grid configuration, declared on its `CorpusMap`. A grid built
with `allow_teleport=True` is a different graph from one built without, so pairs frozen
against one say nothing about the other; one configuration per map is what keeps
`pairs/<map>.json` a plain list of triples.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal, NamedTuple

from maple.model.mechanics.game_file_extraction.map_physics import MinimapPhysics
from maple.model.mechanics.maple_map import MapleMap, MapleMinimap
from maple.model.mechanics.minimap_creation.minimap_edits_model import (
    MinimapEditsManager,
)
from maple.model.mechanics.minimap_creation.minimap_grid import MinimapGrid, MinimapNode
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
)

_LAB_ROOT = Path(__file__).parent
MAPS_ROOT = _LAB_ROOT / "maps"
PAIRS_ROOT = _LAB_ROOT / "pairs"

# The lab compiles as a character with no stat bonuses, so a Movement Plan's lengths
# and the grid's connections are the map's own and not a build's.
_SPEED_MULTIPLIER = 1.0
_JUMP_MULTIPLIER = 1.0

# `MovementHandler` needs a handle and an IGN to name the Actions it would build. The
# lab never sends one, so any values do — these are stable so a cache key is too.
LAB_HANDLE = 0
LAB_IGN = "MovementLab"


@dataclass(frozen=True)
class CorpusMap:
    """One map in the Corpus, with the single grid configuration it is frozen against."""

    name: str
    source: Literal["fixture", "mapfile"]
    allow_teleport: bool
    sample_size: int
    seed: int

    @property
    def pairs_path(self) -> Path:
        return PAIRS_ROOT / f"{self.name}.json"


class Pair(NamedTuple):
    """One frozen sample: where a Path starts, where it ends, and whether it exists."""

    start: tuple[int, int]
    end: tuple[int, int]
    reachable: bool


class PlanRecord(NamedTuple):
    """A Pair resolved against its grid: the Path it produced, and the Movement Plan."""

    pair: Pair
    path: tuple[MinimapNode, ...]
    movements: tuple[_MovementComponent, ...]

    @property
    def movement_types(self) -> frozenset[MovementTypes]:
        return frozenset(component.movement_type for component in self.movements)


# --- The Corpus -------------------------------------------------------------------
#
# Fixture maps first, in coverage order; the real mapfiles after. Each fixture's
# guarantee is asserted in `test_corpus.py` — the matrix is checked, not assumed.

FIXTURE_MAPS: tuple[CorpusMap, ...] = (
    CorpusMap("walk_corridor", "fixture", False, 200, 103_001),
    CorpusMap("ladder_climb", "fixture", False, 300, 103_002),
    CorpusMap("jump_gap", "fixture", False, 200, 103_003),
    CorpusMap("jump_ledge", "fixture", False, 200, 103_004),
    CorpusMap("portal_pair", "fixture", False, 200, 103_005),
    CorpusMap("teleport_shaft", "fixture", True, 300, 103_006),
    CorpusMap("narrow_perch", "fixture", False, 200, 103_007),
)

# `GhostShip1` is the rich one (15 features, an in-map portal, 278 walkable nodes) and
# is frozen with teleport on, the configuration a teleporting class runs it under.
# `Line1Area1` is a single platform: it carries no coverage, only the shape of a real
# 219-node map whose every Path is a walk.
MAPFILES: tuple[CorpusMap, ...] = (
    CorpusMap("GhostShip1", "mapfile", True, 300, 103_101),
    CorpusMap("Line1Area1", "mapfile", False, 200, 103_102),
)

CORPUS: tuple[CorpusMap, ...] = FIXTURE_MAPS + MAPFILES

# What each fixture map exists to force. The union is every movement type
# `path_into_movements` can emit, so the fixtures alone carry the coverage matrix.
FIXTURE_GUARANTEES: dict[str, frozenset[MovementTypes]] = {
    "walk_corridor": frozenset({MovementTypes.WALK_LEFT, MovementTypes.WALK_RIGHT}),
    "ladder_climb": frozenset({MovementTypes.CLIMB_UP, MovementTypes.CLIMB_DOWN}),
    "jump_gap": frozenset({MovementTypes.JUMP_LEFT, MovementTypes.JUMP_RIGHT}),
    "jump_ledge": frozenset({MovementTypes.JUMP, MovementTypes.JUMP_DOWN}),
    "portal_pair": frozenset({MovementTypes.ENTER_PORTAL}),
    "teleport_shaft": frozenset(
        {
            MovementTypes.TELEPORT_LEFT,
            MovementTypes.TELEPORT_RIGHT,
            MovementTypes.TELEPORT_UP,
            MovementTypes.TELEPORT_DOWN,
        }
    ),
    "narrow_perch": frozenset({MovementTypes.JUMP_LEFT, MovementTypes.JUMP_RIGHT}),
}

# `FLASH_JUMP_LEFT`, `FLASH_JUMP_RIGHT` and `CROUCH` have no `ConnectionTypes`
# counterpart (commented out as `NotImplemented` there) and their builders raise, so no
# grid can produce them: unreachable by construction, not a gap in the Corpus.
UNREACHABLE_BY_CONSTRUCTION: frozenset[MovementTypes] = frozenset(
    {
        MovementTypes.FLASH_JUMP_LEFT,
        MovementTypes.FLASH_JUMP_RIGHT,
        MovementTypes.CROUCH,
    }
)

# The 13 rows of the coverage matrix. `END_OF_MOVEMENT` is the sentinel every Movement
# Plan ends with, not a movement, so it is not a row.
REACHABLE_MOVEMENT_TYPES: frozenset[MovementTypes] = (
    frozenset(MovementTypes)
    - UNREACHABLE_BY_CONSTRUCTION
    - {MovementTypes.END_OF_MOVEMENT}
)


# --- Loading ----------------------------------------------------------------------


@cache
def minimap(entry: CorpusMap) -> MapleMinimap:
    """
    The map's `MapleMinimap`, built from its JSON config.

    A real mapfile is loaded the way the bot loads it, through `MapleMap`. A fixture
    map is loaded by path instead: fixtures live under `tests/` deliberately, since
    they describe no real place and the bot must never be able to farm one.
    """
    if entry.source == "mapfile":
        return MapleMap(entry.name).minimap

    edits = MinimapEditsManager.from_file(str(MAPS_ROOT / f"{entry.name}.json"))
    assert edits is not None, f"No fixture map at {MAPS_ROOT / entry.name}.json"
    # Both halves of the scale are needed before a grid can be generated at all; a
    # fixture missing either is a broken fixture, not a map without physics.
    assert edits.scale_x is not None, f"Fixture map {entry.name} has no scale_x"
    assert edits.scale_y is not None, f"Fixture map {entry.name} has no scale_y"
    return MapleMinimap(entry.name, edits, MinimapPhysics(edits.scale_x, edits.scale_y))


@cache
def grid(entry: CorpusMap) -> MinimapGrid:
    """The map's grid, in the one configuration its sample is frozen against."""
    return minimap(entry).generate_grid(
        entry.allow_teleport, _SPEED_MULTIPLIER, _JUMP_MULTIPLIER
    )


@cache
def handler(entry: CorpusMap) -> MovementHandler:
    return MovementHandler(LAB_HANDLE, minimap(entry), LAB_IGN)


@cache
def walkable_nodes(entry: CorpusMap) -> tuple[tuple[int, int], ...]:
    """
    Every walkable coordinate, read off the grid in row-major order.

    Read from the grid and not from `modified_minimap`, because `generate_grid`
    unsets nodes whose feature is unwalkable as it goes: the grid is the state a Path
    is actually computed over.
    """
    return tuple(
        (node.x, node.y) for row in grid(entry).nodes for node in row if node.walkable
    )


# --- The frozen sample ------------------------------------------------------------


def draw_pairs(entry: CorpusMap) -> tuple[tuple[tuple[int, int], tuple[int, int]], ...]:
    """
    Re-derive which start-and-end pairs the sample holds, from the seed alone.

    Deliberately does no pathfinding: this is the half of the frozen file that is a
    pure function of the seed, the sample size and the map's walkable nodes, so it can
    be checked against the file cheaply. The reachability half is checked by walking
    the Paths (see `plans`).
    """
    nodes = walkable_nodes(entry)
    rng = random.Random(entry.seed)
    drawn: list[tuple[tuple[int, int], tuple[int, int]]] = []
    seen: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    # A tiny fixture map has fewer distinct ordered pairs than the sample size asks
    # for; drawing to exhaustion beats looping forever on a map that cannot fill it.
    attempts_left = entry.sample_size * 100
    while len(drawn) < entry.sample_size and attempts_left > 0:
        attempts_left -= 1
        start, end = rng.choice(nodes), rng.choice(nodes)
        if start == end or (start, end) in seen:
            continue
        seen.add((start, end))
        drawn.append((start, end))
    return tuple(drawn)


@cache
def load_sample(entry: CorpusMap) -> tuple[Pair, ...]:
    """The checked-in sample for this map, as `(start, end, reachable)` triples."""
    payload = json.loads(entry.pairs_path.read_text(encoding="utf-8"))
    assert payload["map"] == entry.name, (
        f"{entry.pairs_path.name} was generated for {payload['map']!r}"
    )
    assert payload["allow_teleport"] == entry.allow_teleport, (
        f"{entry.pairs_path.name} was frozen against a different grid configuration: "
        f"allow_teleport={payload['allow_teleport']!r}"
    )
    assert payload["seed"] == entry.seed, (
        f"{entry.pairs_path.name} was generated from seed {payload['seed']}, not "
        f"{entry.seed}"
    )
    return tuple(
        Pair((start[0], start[1]), (end[0], end[1]), reachable)
        for start, end, reachable in payload["pairs"]
    )


def render_sample(entry: CorpusMap, pairs: tuple[Pair, ...]) -> str:
    """
    The file's exact text, so the generator and the format check share one renderer.

    One pair per line, which keeps a diff on a regenerated sample readable: a pair
    whose reachability changed is one changed line, not a reflowed block.
    """
    lines = [
        "{",
        f'  "map": {json.dumps(entry.name)},',
        f'  "allow_teleport": {json.dumps(entry.allow_teleport)},',
        f'  "seed": {entry.seed},',
        f'  "count": {len(pairs)},',
        '  "pairs": [',
    ]
    rendered = [
        f"    [[{p.start[0]}, {p.start[1]}], [{p.end[0]}, {p.end[1]}], "
        f"{json.dumps(p.reachable)}]"
        for p in pairs
    ]
    lines.append(",\n".join(rendered))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def freeze_sample(entry: CorpusMap) -> tuple[Pair, ...]:
    """
    Compute the sample from scratch: draw the pairs, then resolve each one's
    reachability against the grid. This is what the generator writes and what the
    lab's checks compare against.
    """
    return tuple(
        Pair(start, end, bool(compute_path(entry, start, end)))
        for start, end in draw_pairs(entry)
    )


# --- Paths and Movement Plans -----------------------------------------------------


def compute_path(
    entry: CorpusMap, start: tuple[int, int], end: tuple[int, int]
) -> tuple[MinimapNode, ...]:
    return handler(entry).compute_path(start, end, grid(entry))


@cache
def plans(entry: CorpusMap) -> tuple[PlanRecord, ...]:
    """
    Every pair in the frozen sample, resolved to its Path and Movement Plan.

    Cached for the session: a Path is computed once and every check in the lab reads
    it from here, so the suite pays for the corpus once rather than per test.
    """
    records = []
    for pair in load_sample(entry):
        path = compute_path(entry, pair.start, pair.end)
        movements = (
            handler(entry).path_into_movements(path, grid(entry)) if path else ()
        )
        records.append(PlanRecord(pair, path, movements))
    return tuple(records)


def movement_types_in(entry: CorpusMap) -> frozenset[MovementTypes]:
    """Every movement type this map's frozen sample produces."""
    return frozenset().union(*(record.movement_types for record in plans(entry)))
