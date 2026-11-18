"""
Platforms and walls: a map's own footholds, chained by `prev`/`next`.

A **wall** is a vertical foothold (`x1 == x2`). A **platform** is a maximal
chain of non-vertical footholds in one layer, each the `next` of the one
before it; slopes stay in it, and a chain ends where it meets a wall.

**Which links count.** A link joins two footholds only when both agree: `a`
names `b` as its `next`, and `b` names `a` as its `prev`, in the same layer.
The client's files have one-sided links, where two footholds both claim the
same neighbour (21 in Ellinia, each a fork left by the map's editor); a link
counted from one side would give a foothold two successors, and a platform
would no longer be a chain. A link to a foothold that doesn't exist, to one in
another layer, or to a wall, is dropped likewise. So every non-wall foothold
lies on exactly one platform, whatever the links say.

A chain that closes on itself is opened before its lowest foothold ID.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from game_data.catalogue import Foothold

type _Key = tuple[int | None, int]
"""A foothold's layer and ID: IDs are looked up within one layer only."""


@dataclass(frozen=True, slots=True)
class Platform:
    """
    A maximal chain of non-vertical footholds, in virtual px.

    :ivar layer: The foothold layer its footholds are in.
    :ivar footholds: In chain order: each is the `next` of the one before it.
    """

    layer: int | None
    footholds: tuple[Foothold, ...]

    @property
    def left(self) -> int:
        """Its leftmost x."""
        return min(min(f.x1, f.x2) for f in self.footholds)

    @property
    def right(self) -> int:
        """Its rightmost x."""
        return max(max(f.x1, f.x2) for f in self.footholds)

    def y_at(self, x: float) -> float | None:
        """
        Its height at `x`, along the first of its footholds that spans it;
        `None` when none does.
        """
        for f in self.footholds:
            low, high = min(f.x1, f.x2), max(f.x1, f.x2)
            if low <= x <= high:
                return f.y1 + (f.y2 - f.y1) * (x - f.x1) / (f.x2 - f.x1)
        return None


def is_wall(foothold: Foothold) -> bool:
    """A vertical foothold."""
    return foothold.x1 == foothold.x2


def chain_platforms(
    footholds: Iterable[Foothold],
) -> tuple[tuple[Platform, ...], tuple[Foothold, ...]]:
    """
    The platforms and the walls of a map's own footholds.

    :param footholds: The map's own (`source == "map"`); a foothold drawn on an
        object or a tile has no `prev`/`next`, and isn't passed.
    :returns: The platforms, ordered by their first foothold's layer and ID;
        and the walls, in the order given.
    """
    given = list(footholds)
    walls = tuple(f for f in given if is_wall(f))
    ground = {_key(f): f for f in given if not is_wall(f)}

    def agreed_next(f: Foothold) -> Foothold | None:
        after = ground.get((f.layer, f.next or 0)) if f.next else None
        return after if after is not None and after.prev == f.id else None

    def agreed_prev(f: Foothold) -> Foothold | None:
        before = ground.get((f.layer, f.prev or 0)) if f.prev else None
        return before if before is not None and before.next == f.id else None

    platforms: list[Platform] = []
    placed: set[_Key] = set()
    starts = [f for f in ground.values() if agreed_prev(f) is None]
    for start in sorted(starts, key=_order):
        chain = _follow(start, agreed_next)
        placed.update(_key(f) for f in chain)
        platforms.append(Platform(start.layer, chain))
    # What is left closes on itself: open each loop before its lowest ID.
    for f in sorted(ground.values(), key=_order):
        if _key(f) not in placed:
            chain = _follow(f, agreed_next)
            placed.update(_key(g) for g in chain)
            platforms.append(Platform(f.layer, chain))
    platforms.sort(key=lambda p: _order(p.footholds[0]))
    return tuple(platforms), walls


def _follow(
    start: Foothold, after: Callable[[Foothold], Foothold | None]
) -> tuple[Foothold, ...]:
    chain = [start]
    seen = {_key(start)}
    current = after(start)
    while current is not None and _key(current) not in seen:
        chain.append(current)
        seen.add(_key(current))
        current = after(current)
    return tuple(chain)


def _key(f: Foothold) -> _Key:
    return (f.layer, f.id)


def _order(f: Foothold) -> tuple[int, int]:
    return (f.layer if f.layer is not None else -1, f.id)
