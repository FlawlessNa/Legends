"""
The movement lab's Fixture maps: synthetic `MapData`, each built to force the
movement types it is named for (`corpus.FIXTURE_GUARANTEES` says which, and
`test_corpus.py` checks it).

They describe no real place, and live under `tests/` so the bot can never be
pointed at one. Coordinates are virtual px, y growing downwards; the lab's
physics (`corpus.LAB_PHYSICS`, the client's own `Physics.img` values) jump
77 px high and 69 px far, so:

- a gap of 40 to 60 px is jumped, never walked or fallen across;
- a platform 50 px above another is reached by jumping up through it, and
  left by dropping down;
- a rope whose bottom hangs 40 px above the ground is reached by a jump only;
- platforms 110 px apart vertically are out of a jump's reach, but within a
  teleport's (150 px).
"""

from itertools import pairwise

from game_data.catalogue import Bounds, Foothold, MapData, Minimap, Portal, Rope

#: Every fixture's minimap: the canvas at 16 virtual px per pixel (`mag` 4, as
#: every MSCW map), centred so the fixtures' coordinates land on it.
_MINIMAP = Minimap(center_x=1000, center_y=1000, mag=4, width=3000, height=2000)


def _footholds(*segments: tuple[int, int, int, int]) -> tuple[Foothold, ...]:
    """Each segment `(x1, y1, x2, y2)` its own platform: no prev/next links."""
    return tuple(
        Foothold("map", 0, 1, i, x1, y1, x2, y2, 0, 0)
        for i, (x1, y1, x2, y2) in enumerate(segments, start=1)
    )


def _chain(first_id: int, *points: tuple[int, int]) -> tuple[Foothold, ...]:
    """One platform through `points`, its footholds linked by prev/next."""
    ids = range(first_id, first_id + len(points) - 1)
    return tuple(
        Foothold(
            "map",
            0,
            1,
            fid,
            x1,
            y1,
            x2,
            y2,
            fid - 1 if fid > first_id else 0,
            fid + 1 if fid < first_id + len(points) - 2 else 0,
        )
        for fid, ((x1, y1), (x2, y2)) in zip(ids, pairwise(points), strict=True)
    )


def _rope(rope_id: int, x: int, top: int, bottom: int, *, ladder: bool) -> Rope:
    return Rope("map", rope_id, x, top, bottom, ladder, True, 0)


def _map(
    map_id: int,
    name: str,
    footholds: tuple[Foothold, ...],
    ropes: tuple[Rope, ...] = (),
    portals: tuple[Portal, ...] = (),
) -> MapData:
    return MapData(
        id=map_id,
        name=name,
        street="Movement Lab",
        vr=Bounds(-1000, -1000, 2000, 1000),
        vr_derived=False,
        minimap=_MINIMAP,
        town=False,
        swim=False,
        fly=False,
        field_limit=0,
        bgm=None,
        return_map=None,
        footholds=footholds,
        ropes=ropes,
        portals=portals,
        spawns=(),
    )


def walk_corridor() -> MapData:
    """One long floor, two platforms joined end to end with a slope between."""
    return _map(
        900_000_001,
        "walk_corridor",
        _chain(1, (0, 0), (300, 0), (400, -20), (700, -20)),
    )


def ladder_climb() -> MapData:
    """
    A floor, and a shelf 500 px above it joined to it by a ladder. The shelf is
    out of a drop's reach (480 px) and walled at both ends, so it is left by the
    ladder only, and reached by it only.
    """
    return _map(
        900_000_002,
        "ladder_climb",
        _footholds(
            (0, 0, 600, 0),
            (200, -500, 500, -500),
            (200, -560, 200, -500),
            (500, -560, 500, -500),
        ),
        (_rope(1, 300, -498, 0, ladder=True),),
    )


def jump_gap() -> MapData:
    """Three platforms in a row, 50 px apart: each gap a jump, either way."""
    return _map(
        900_000_003,
        "jump_gap",
        _footholds((0, 0, 200, 0), (250, 0, 450, 0), (500, 0, 700, 0)),
    )


def jump_ledge() -> MapData:
    """A floor with a shelf 50 px above its middle: jump up onto it, drop off it."""
    return _map(
        900_000_004,
        "jump_ledge",
        _footholds((0, 0, 600, 0), (200, -50, 400, -50)),
    )


def portal_pair() -> MapData:
    """
    Two floors no move joins, and a portal from the lower to the upper only: so
    the sample holds unreachable pairs too.
    """
    return _map(
        900_000_005,
        "portal_pair",
        _footholds((0, 0, 300, 0), (600, -400, 900, -400)),
        portals=(
            Portal("up", 0, 150, 0, 900_000_005, "down"),
            Portal("down", 0, 750, -400, None, None),
        ),
    )


def teleport_shaft() -> MapData:
    """
    Platforms 110 px above each other (no jump reaches) and 140 px apart side
    to side over a pit, for a character with teleport: each way is a teleport.
    """
    return _map(
        900_000_006,
        "teleport_shaft",
        _footholds(
            (0, 0, 100, 0),
            (0, -110, 100, -110),
            (0, -220, 100, -220),
            (240, 0, 340, 0),
            (240, -110, 340, -110),
        ),
    )


def narrow_perch() -> MapData:
    """
    Two floors with a 40 px perch between them, 50 px from each: narrow, and
    still wide enough for a jump to land `LANDING_MARGIN` inside both its ends.
    """
    return _map(
        900_000_007,
        "narrow_perch",
        _footholds((0, 0, 200, 0), (250, 0, 290, 0), (340, 0, 540, 0)),
    )


def rope_grab() -> MapData:
    """
    A floor, and a shelf 200 px above it with two ropes hanging from it, their
    bottoms 40 px above the floor: each is grabbed by a jump, straight up from
    under it or sideways. The right one is walled on both sides along all but
    its top, so no sideways jump leaves it: it is left by climbing up onto the
    shelf, or by climbing down past its bottom and falling off.
    """
    return _map(
        900_000_008,
        "rope_grab",
        _footholds(
            (0, 0, 800, 0),
            (200, -200, 600, -200),
            (490, -195, 490, -30),
            (510, -195, 510, -30),
        ),
        (
            _rope(1, 300, -198, -40, ladder=False),
            _rope(2, 500, -198, -40, ladder=False),
        ),
    )


FIXTURES = {
    builder.__name__: builder
    for builder in (
        walk_corridor,
        ladder_climb,
        jump_gap,
        jump_ledge,
        portal_pair,
        teleport_shaft,
        narrow_perch,
        rope_grab,
    )
}
