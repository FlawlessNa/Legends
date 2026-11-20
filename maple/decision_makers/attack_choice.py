"""
Which attack a decision of `MobsHitting` casts, and which way it faces (spec
#631 § 4, "On screen" and "A mob is in reach", and § 6, "Each decision"): pure
functions of the profile's attacks, the mobs found on one frame, and where the
character stands on it.

An attack's reach is a box around the feet in virtual px, facing left
(`maple.model.characters.reach`). On screen it is placed at the character's
feet, the bottom-centre of its `x1, y1, x2, y2` box, scaled to client px by the
frame's size over `camera.play_area_size(client_size)`, and its bottom is cut at
the chat's top. A mob is in reach when its detection box overlaps the placed
reach by at least one pixel on each axis: an attack box against a body box, as
the game decides.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from maple.model.characters.reach import Reach, Sides

from .providers.attacks import Attack, Facing

#: A detection box in client px: `x1, y1, x2, y2`.
ClientBox = tuple[int, int, int, int]
#: Which way a one-sided cast faces, as `cast_skill`'s `direction` takes it.
Side = Literal["left", "right"]
SIDES: tuple[Side, Side] = ("left", "right")


@dataclass(frozen=True, slots=True)
class Placement:
    """
    Where a reach goes on one frame.

    :ivar feet: The character's feet in client px: the bottom-centre of its box.
    :ivar scale: Client px per virtual px, horizontally and vertically: the
        frame's size over the play area's.
    :ivar bottom: The chat's top in client px; nothing below it is reached.
    """

    feet: tuple[float, float]
    scale: tuple[float, float]
    bottom: float

    def place(
        self, reach: Reach, side: Side | None
    ) -> tuple[float, float, float, float]:
        """
        `reach` in client px, facing `side`: left for None, as the client stores
        it (a two-sided reach is the same either way).
        """
        box = reach.facing_right() if side == "right" else reach
        fx, fy = self.feet
        sx, sy = self.scale
        return (
            fx + box.lt_x * sx,
            fy + box.lt_y * sy,
            fx + box.rb_x * sx,
            min(fy + box.rb_y * sy, self.bottom),
        )

    def offset(self, mob: ClientBox) -> ClientBox:
        """The mob's box from the feet, in whole client px."""
        fx, fy = self.feet
        x1, y1, x2, y2 = mob
        return (round(x1 - fx), round(y1 - fy), round(x2 - fx), round(y2 - fy))

    def distance(self, mob: ClientBox) -> float:
        """How far the mob's box centre is from the feet, horizontally."""
        return abs((mob[0] + mob[2]) / 2 - self.feet[0])


def placement(
    character: Sequence[int],
    client_size: tuple[int, int],
    play_area: tuple[int, int],
    chat_top: float,
) -> Placement:
    """
    :param character: The character's on-screen box, `x1, y1, x2, y2`.
    :param client_size: The frame's width and height.
    :param play_area: `camera.play_area_size(client_size)`.
    :param chat_top: Where the chat starts; the frame's bottom when it isn't
        found.
    """
    x1, _y1, x2, y2 = character
    return Placement(
        feet=((x1 + x2) / 2, float(y2)),
        scale=(client_size[0] / play_area[0], client_size[1] / play_area[1]),
        bottom=chat_top,
    )


def overlaps(mob: ClientBox, box: tuple[float, float, float, float]) -> bool:
    """Whether the mob's box and `box` share at least one pixel on each axis."""
    x1, y1, x2, y2 = mob
    left, top, right, bottom = box
    return min(x2, right) - max(x1, left) >= 1 and min(y2, bottom) - max(y1, top) >= 1


def in_reach(
    reach: Reach, side: Side | None, mobs: Iterable[ClientBox], where: Placement
) -> tuple[ClientBox, ...]:
    """The mobs whose box overlaps `reach` placed facing `side`."""
    box = where.place(reach, side)
    return tuple(mob for mob in mobs if overlaps(mob, box))


def counted(
    attack: Attack, mobs: Sequence[ClientBox], where: Placement
) -> dict[Side | None, tuple[ClientBox, ...]]:
    """
    The mobs in the attack's reach: once, under None, for a two-sided reach;
    facing left and facing right for a one-sided one.
    """
    return {side: in_reach(attack.reach, side, mobs, where) for side in _sides(attack)}


def _sides(attack: Attack) -> tuple[Side | None, ...]:
    """The sides a cast of the attack is counted on: None, with no facing, for a
    two-sided reach; left and right for a one-sided one."""
    return (None,) if attack.sides is Sides.TWO else SIDES


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
        sides: dict[Side | None, tuple[ClientBox, ...]] = {
            side: found
            for side, found in counted(attack, mobs, where).items()
            if len(found) >= attack.min_mobs
        }
        if not sides:
            continue
        side = _facing(sides, where, facing)
        return Choice(attack, side, sides[side])
    return None


def _facing(
    sides: dict[Side | None, tuple[ClientBox, ...]], where: Placement, facing: Facing
) -> Side | None:
    """
    `closest`: the side of the counted mob nearest the feet, by horizontal
    distance to its box centre, left on a tie. `most`: the side with more
    counted mobs, `closest`'s on a tie.
    """
    if len(sides) == 1:
        return next(iter(sides))
    closest = min(sides, key=lambda side: min(map(where.distance, sides[side])))
    if facing is Facing.MOST:
        most = max(len(found) for found in sides.values())
        leaders: list[Side | None] = [
            side for side, found in sides.items() if len(found) == most
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
        if attack.swings is None:
            continue
        found: list[ClientBox] = []
        for side in _sides(attack):
            reached = set(in_reach(attack.reach, side, mobs, where))
            swung = {
                mob
                for swing in attack.swings
                for mob in in_reach(swing, side, mobs, where)
            }
            found += [m for m in mobs if m in swung - reached and m not in found]
        if found:
            return attack, tuple(found)
    return None
