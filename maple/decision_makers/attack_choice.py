"""
Which attack a decision of `MobsHitting` casts, and which way it faces (spec
#631 § 6, "Each decision"): pure functions of the profile's attacks, the mobs
found on one frame, and where the character stands on it.

Where a reach goes on the frame, and which mobs it holds, is
`maple.model.characters.placed_reach`'s: placed on screen
(`Placement.on_screen`), at least one client px of overlap on each axis.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from maple.model.characters.placed_reach import (
    Placement,
    Side,
    counted,
    in_reach,
    sides,
)

from .providers.attacks import Attack, Facing

#: A detection box in client px: `x1, y1, x2, y2`.
ClientBox = tuple[int, int, int, int]


@dataclass(frozen=True, slots=True)
class Choice:
    """
    The attack a decision casts.

    :ivar attack: The first of the list with enough mobs in reach on a side.
    :ivar direction: The side it faces; None for a two-sided attack, which is
        cast with no facing prelude.
    :ivar mobs: The mobs counted on that side.
    """

    attack: Attack
    direction: Side | None
    mobs: tuple[ClientBox, ...]


def choose(
    attacks: Iterable[Attack],
    mobs: Sequence[ClientBox],
    where: Placement,
    facing: Facing,
) -> Choice | None:
    """
    The first attack with a side counting at least its `min_mobs`, facing as
    `facing` says among the sides that do; None when no attack fires.
    """
    for attack in attacks:
        firing: dict[Side | None, tuple[ClientBox, ...]] = {
            side: found
            for side, found in counted(attack.reach, mobs, where).items()
            if len(found) >= attack.min_mobs
        }
        if not firing:
            continue
        side = _facing(firing, where, facing)
        return Choice(attack, side, firing[side])
    return None


def _facing(
    firing: dict[Side | None, tuple[ClientBox, ...]], where: Placement, facing: Facing
) -> Side | None:
    """
    `closest`: the side of the counted mob nearest the feet, by horizontal
    distance to its box centre, left on a tie. `most`: the side with more
    counted mobs, `closest`'s on a tie.
    """
    if len(firing) == 1:
        return next(iter(firing))
    closest = min(firing, key=lambda side: min(map(where.distance, firing[side])))
    if facing is Facing.MOST:
        most = max(len(found) for found in firing.values())
        leaders: list[Side | None] = [
            side for side, found in firing.items() if len(found) == most
        ]
        if len(leaders) == 1:
            return leaders[0]
    return closest


def partial(
    attacks: Iterable[Attack], mobs: Sequence[ClientBox], where: Placement
) -> tuple[Attack, tuple[ClientBox, ...]] | None:
    """
    The first weapon-based attack with mobs whose box overlaps one of its
    swings but not their overlap, its reach, on either side; with those mobs.
    None when no attack has any.
    """
    for attack in attacks:
        if attack.armed.swings is None:
            continue
        found: list[ClientBox] = []
        for side in sides(attack.reach):
            reached = set(in_reach(attack.reach, side, mobs, where))
            swung = {
                mob
                for swing in attack.armed.swings
                for mob in in_reach(swing, side, mobs, where)
            }
            found += [m for m in mobs if m in swung - reached and m not in found]
        if found:
            return attack, tuple(found)
    return None
