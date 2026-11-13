"""
The Corpus the movement lab compiles against: the maps, and the frozen sample of
start-and-end pairs per map.

Two tiers, per issue #10. **Fixture maps** are synthetic `MapData`
(`fixture_maps.py`), each built to force one movement type, and they carry the
coverage matrix, so coverage never depends on whether a real map happens to
contain a jump-down. They run in the default suite. **Real maps** come from the
game data store (`game_data`) and carry realism; they need the client's files,
so they run under the `client_files` marker (`CLIENT_MAPS`).

Every map is a `WorldMap`; Paths are planned on its `FootholdGraph` and turned
into Movement Plans by `MovementHandler`, in virtual px (#396), with the client's
own physics and no stat bonuses (`LAB_PHYSICS`).

The sample is *frozen*: `pairs/<map>.json` is generated once from a fixed seed and
checked in, with each pair's reachability recorded as **data**. Nothing here queries
reachability at runtime, so a pair that stops being reachable fails a check instead of
being silently skipped. Regenerate with `python toolkit/generate_movement_lab_pairs.py`.

Every map fixes **one** graph configuration, declared on its `CorpusMap`: a graph
built with teleport moves is a different graph from one without, so pairs frozen
against one say nothing about the other.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from functools import cache, lru_cache
from pathlib import Path
from typing import Literal, NamedTuple

from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics.movement_mechanics_v2 import (
    MovementHandler,
    MovementTypes,
    _MovementComponent,
)
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import FootholdGraph
from maple.model.navigation import Path as GraphPath
from maple.model.world import WorldMap
from tests.test_maple.movement_lab.fixture_maps import FIXTURES

_LAB_ROOT = Path(__file__).parent
PAIRS_ROOT = _LAB_ROOT / "pairs"

#: The client's own `Map/Physics.img` values (`walkSpeed`, `jumpSpeed`,
#: `gravityAcc`, `fallSpeed`, `walkForce`, `walkDrag`), as the game data store
#: holds them: written out
#: so the default suite needs no store. The lab plans as a character with no
#: stat bonuses and no Calibration constants, so a Movement Plan's lengths and
#: times are the map's own and not a build's.
LAB_PHYSICS_VALUES = {
    "walkSpeed": 125.0,
    "jumpSpeed": 555.0,
    "gravityAcc": 2000.0,
    "fallSpeed": 670.0,
    "walkForce": 140000.0,
    "walkDrag": 80000.0,
}
LAB_PHYSICS = VRPhysics.from_game_files(LAB_PHYSICS_VALUES)

# `MovementHandler` needs a handle and an IGN to name the Actions it would build. The
# lab never sends one, so any values do — these are stable so a cache key is too.
LAB_HANDLE = 0
LAB_IGN = "MovementLab"

#: Virtual px between two candidate start or end points along a surface.
POINT_SPACING = 4


@dataclass(frozen=True)
class _StubTeleportSkill(MapleSkill):
    """
    A `Skill` whose key bind does not go through the gitignored keybindings config -
    same shape as `tests/test_botting/test_telecast.py`'s `_StubSkill`.
    """

    key: str = field(default="insert", repr=False)

    @lru_cache  # noqa: B019
    def key_bind(self, ign: str) -> str:
        return self.key


#: The Teleport skill a map frozen with teleport moves is planned and compiled with.
LAB_TELEPORT = _StubTeleportSkill("Teleport", "Movement", animation_time=0.15)


@dataclass(frozen=True)
class CorpusMap:
    """
    One map in the Corpus, with the single graph configuration it is frozen against.

    :ivar name: A Fixture map's name (`fixture_maps.FIXTURES`), or a real map's
        name as `Catalogue.map` resolves it.
    """

    name: str
    source: Literal["fixture", "client"]
    teleport: bool
    sample_size: int
    seed: int

    @property
    def pairs_path(self) -> Path:
        return PAIRS_ROOT / f"{self.file_stem}.json"

    @property
    def file_stem(self) -> str:
        return self.name.replace(":", "").replace(" ", "_")


class Pair(NamedTuple):
    """One frozen sample: where a Path starts, where it ends, and whether it exists."""

    start: tuple[float, float]
    end: tuple[float, float]
    reachable: bool


class PlanRecord(NamedTuple):
    """A Pair resolved against its graph: the Path it produced, and the Movement Plan."""

    pair: Pair
    path: GraphPath | None
    movements: tuple[_MovementComponent, ...]

    @property
    def movement_types(self) -> frozenset[MovementTypes]:
        return frozenset(component.movement_type for component in self.movements)


# --- The Corpus -------------------------------------------------------------------
#
# Fixture maps first, in coverage order; the real maps after. Each fixture's
# guarantee is asserted in `test_corpus.py` — the matrix is checked, not assumed.

FIXTURE_MAPS: tuple[CorpusMap, ...] = (
    CorpusMap("walk_corridor", "fixture", False, 200, 103_001),
    CorpusMap("ladder_climb", "fixture", False, 300, 103_002),
    CorpusMap("jump_gap", "fixture", False, 200, 103_003),
    CorpusMap("jump_ledge", "fixture", False, 200, 103_004),
    CorpusMap("portal_pair", "fixture", False, 200, 103_005),
    CorpusMap("teleport_shaft", "fixture", True, 300, 103_006),
    CorpusMap("narrow_perch", "fixture", False, 200, 103_007),
    CorpusMap("rope_grab", "fixture", False, 300, 103_008),
)

# Ellinia is the epic's done-line map (#400): platforms, ropes, ladders and jumps,
# frozen with teleport on, as a teleporting class runs it. Damp Forest is the other
# map the frame sets cover.
CLIENT_MAPS: tuple[CorpusMap, ...] = (
    CorpusMap("Victoria Road: Ellinia", "client", True, 300, 103_101),
    CorpusMap("Damp Forest", "client", False, 200, 103_102),
)

CORPUS: tuple[CorpusMap, ...] = FIXTURE_MAPS + CLIENT_MAPS

# What each fixture map exists to force. The union is every movement type
# `path_into_movements` emits from a graph Path, so the fixtures alone carry the
# coverage matrix.
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
        }
    ),
    "narrow_perch": frozenset({MovementTypes.JUMP_LEFT, MovementTypes.JUMP_RIGHT}),
    "rope_grab": frozenset(
        {MovementTypes.JUMP, MovementTypes.CLIMB_UP, MovementTypes.CLIMB_DOWN}
    ),
}

# `FLASH_JUMP_LEFT`, `FLASH_JUMP_RIGHT` and `CROUCH` have no graph move and their
# builders raise, so no Path can produce them: unreachable by construction, not a
# gap in the Corpus.
UNREACHABLE_BY_CONSTRUCTION: frozenset[MovementTypes] = frozenset(
    {
        MovementTypes.FLASH_JUMP_LEFT,
        MovementTypes.FLASH_JUMP_RIGHT,
        MovementTypes.CROUCH,
    }
)

# `TELEPORT_DOWN` is a graph move, but the graph never plans it: a teleport down
# lands where drops do (the lowest platform within its reach, which drops reach one
# platform at a time), and costs `TELEPORT_TIME` (0.74 s) where a drop of up to the
# teleport's reach falls in under 0.4 s. Not a gap in the Corpus: no map can make it
# the quickest move. Its compiled shape is checked by hand-built plans
# (`tests/test_botting/test_skill_key_closure.py`).
NEVER_PLANNED: frozenset[MovementTypes] = frozenset({MovementTypes.TELEPORT_DOWN})

# The rows of the coverage matrix. `END_OF_MOVEMENT` is the sentinel every Movement
# Plan ends with, not a movement, so it is not a row.
REACHABLE_MOVEMENT_TYPES: frozenset[MovementTypes] = (
    frozenset(MovementTypes)
    - UNREACHABLE_BY_CONSTRUCTION
    - NEVER_PLANNED
    - {MovementTypes.END_OF_MOVEMENT}
)


# --- Loading ----------------------------------------------------------------------


@cache
def world_map(entry: CorpusMap) -> WorldMap:
    """
    The map's `WorldMap`: a Fixture map's from its synthetic `MapData`, a real
    map's from the game data store, as the bot loads it.
    """
    if entry.source == "fixture":
        return WorldMap.from_map_data(FIXTURES[entry.name]())
    return WorldMap.load(entry.name)


@cache
def handler(entry: CorpusMap) -> MovementHandler:
    """
    The map's `MovementHandler`, in the one configuration its sample is frozen
    against: with a teleport skill when the map is frozen with teleport moves.
    """
    teleport = LAB_TELEPORT if entry.teleport else None
    return MovementHandler(LAB_HANDLE, world_map(entry), LAB_IGN, teleport)


def graph(entry: CorpusMap) -> FootholdGraph:
    """The map's graph, on the lab's physics."""
    return handler(entry).graph(LAB_PHYSICS)


@cache
def candidate_points(entry: CorpusMap) -> tuple[tuple[float, float], ...]:
    """
    Every point a sample may start or end at: every `POINT_SPACING` virtual px
    along each platform (on its line) and each rope, in the map's order.
    """
    wm = world_map(entry)
    points: list[tuple[float, float]] = []
    for platform in wm.platforms:
        for x in range(
            math.ceil(platform.left), math.floor(platform.right) + 1, POINT_SPACING
        ):
            y = platform.y_at(x)
            if y is not None:
                points.append((float(x), round(float(y), 3)))
    for rope in wm.ropes:
        top, bottom = min(rope.y1, rope.y2), max(rope.y1, rope.y2)
        for y in range(top, bottom + 1, POINT_SPACING):
            points.append((float(rope.x), float(y)))
    return tuple(points)


# --- The frozen sample ------------------------------------------------------------


def draw_pairs(
    entry: CorpusMap,
) -> tuple[tuple[tuple[float, float], tuple[float, float]], ...]:
    """
    Re-derive which start-and-end pairs the sample holds, from the seed alone.

    Deliberately does no pathfinding: this is the half of the frozen file that is a
    pure function of the seed, the sample size and the map's candidate points, so it
    can be checked against the file cheaply. The reachability half is checked by
    planning the Paths (see `plans`).
    """
    points = candidate_points(entry)
    rng = random.Random(entry.seed)
    drawn: list[tuple[tuple[float, float], tuple[float, float]]] = []
    seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    # A tiny fixture map has fewer distinct ordered pairs than the sample size asks
    # for; drawing to exhaustion beats looping forever on a map that cannot fill it.
    attempts_left = entry.sample_size * 100
    while len(drawn) < entry.sample_size and attempts_left > 0:
        attempts_left -= 1
        start, end = rng.choice(points), rng.choice(points)
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
    assert payload["teleport"] == entry.teleport, (
        f"{entry.pairs_path.name} was frozen against a different graph configuration: "
        f"teleport={payload['teleport']!r}"
    )
    assert payload["seed"] == entry.seed, (
        f"{entry.pairs_path.name} was generated from seed {payload['seed']}, not "
        f"{entry.seed}"
    )
    return tuple(
        Pair(
            (float(start[0]), float(start[1])), (float(end[0]), float(end[1])), bool(r)
        )
        for start, end, r in payload["pairs"]
    )


def _number(value: float) -> str:
    return json.dumps(int(value) if float(value).is_integer() else value)


def render_sample(entry: CorpusMap, pairs: tuple[Pair, ...]) -> str:
    """
    The file's exact text, so the generator and the format check share one renderer.

    One pair per line, which keeps a diff on a regenerated sample readable: a pair
    whose reachability changed is one changed line, not a reflowed block.
    """
    lines = [
        "{",
        f'  "map": {json.dumps(entry.name)},',
        f'  "teleport": {json.dumps(entry.teleport)},',
        f'  "seed": {entry.seed},',
        f'  "count": {len(pairs)},',
        '  "pairs": [',
    ]
    rendered = [
        f"    [[{_number(p.start[0])}, {_number(p.start[1])}], "
        f"[{_number(p.end[0])}, {_number(p.end[1])}], {json.dumps(p.reachable)}]"
        for p in pairs
    ]
    lines.append(",\n".join(rendered))
    lines.append("  ]")
    lines.append("}")
    return "\n".join(lines) + "\n"


def freeze_sample(entry: CorpusMap) -> tuple[Pair, ...]:
    """
    Compute the sample from scratch: draw the pairs, then resolve each one's
    reachability against the graph. This is what the generator writes and what the
    lab's checks compare against.
    """
    return tuple(
        Pair(start, end, compute_path(entry, start, end) is not None)
        for start, end in draw_pairs(entry)
    )


# --- Paths and Movement Plans -----------------------------------------------------


def compute_path(
    entry: CorpusMap, start: tuple[float, float], end: tuple[float, float]
) -> GraphPath | None:
    return handler(entry).compute_path(start, end, LAB_PHYSICS)


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
        movements = handler(entry).path_into_movements(path)
        records.append(PlanRecord(pair, path, movements))
    return tuple(records)


def movement_types_in(entry: CorpusMap) -> frozenset[MovementTypes]:
    """Every movement type this map's frozen sample produces."""
    return frozenset().union(*(record.movement_types for record in plans(entry)))
