"""
Which mobs a reach touches, placed at the character's feet (spec #631 § 4, "On
screen" and "A mob is in reach"): the one answer `MobsHitting` and the Hunting
Area rotation both read (#664).

A `Reach` is a box around the feet in virtual px, facing left as the client
stores it (`maple.model.characters.reach`). A `Placement` puts it somewhere: at
the feet, scaled into the units the mobs' boxes are in, mirrored for a cast
facing right, and cut at a `bottom` when one is given. Two placements exist:

- **On screen** (`Placement.on_screen`), as `MobsHitting` places it: the mobs'
  boxes are in client px, so the reach is scaled from virtual px by the frame's
  size over the play area's, and cut at the chat's top.
- **In virtual px** (`Placement.in_virtual_px`), as the rotation places it at a
  spot of the map: the mobs' boxes were placed through the frame's Camera, so
  the reach is used as the client stores it, with nothing cut.

**A mob is in reach** when its box overlaps the placed reach by at least
`MIN_OVERLAP`, one **client** px, on each axis: an attack box against a body
box, as the game decides. In virtual px that is one client px converted with
the placement's scale. Whether the game hits a mob under one px of overlap is
not known (#661): this is the maintainer's working answer.

A two-sided reach is counted once, under None: a cast of it faces nothing. A
one-sided one is counted facing left and facing right (`counted`).
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Final, Literal

from .reach import Reach, Sides

#: A box, `left, top, right, bottom`, in a placement's units.
type Box = tuple[float, float, float, float]
#: Which way a one-sided cast faces, as `cast_skill`'s `direction` takes it.
type Side = Literal["left", "right"]
SIDES: Final[tuple[Side, Side]] = ("left", "right")

#: How far, in client px on each axis, a mob's box must overlap a reach to be
#: in it: one whole pixel.
MIN_OVERLAP: Final = 1.0
#: How far under `MIN_OVERLAP` an overlap may fall and still count, in client
#: px: float error only. A box placed through the Camera is a whole number of
#: client px times a scale, and converting it back may land a hair under.
_FLOAT_ERROR: Final = 1e-9


class Units(Enum):
    """What a placement's feet, bottom and mob boxes are measured in."""

    #: The frame's pixels: the reach is scaled to them.
    CLIENT = "client px"
    #: The map's: the reach is as the client stores it.
    VIRTUAL = "virtual px"


@dataclass(frozen=True, slots=True)
class Placement:
    """
    Where a reach goes, and in what units the mobs it is tested against are.

    :ivar feet: The character's feet, in `units`.
    :ivar scale: Client px per virtual px, horizontally and vertically: the
        frame's size over the play area's.
    :ivar bottom: Nothing below it is reached, in `units`: the chat's top on
        screen. None cuts nothing.
    :ivar units: What `feet`, `bottom` and the mobs' boxes are in.
    """

    feet: tuple[float, float]
    scale: tuple[float, float]
    bottom: float | None = None
    units: Units = Units.CLIENT

    @classmethod
    def on_screen(
        cls,
        character: Sequence[float],
        client_size: tuple[int, int],
        play_area: tuple[int, int],
        chat_top: float,
    ) -> Placement:
        """
        A reach on one frame, against mobs found on it in client px.

        :param character: The character's on-screen box, `x1, y1, x2, y2`: the
            feet are its bottom-centre.
        :param client_size: The frame's width and height.
        :param play_area: `camera.play_area_size(client_size)`.
        :param chat_top: Where the chat starts; the frame's bottom when it isn't
            found.
        """
        x1, _y1, x2, y2 = character
        return cls(
            feet=((x1 + x2) / 2, float(y2)),
            scale=(client_size[0] / play_area[0], client_size[1] / play_area[1]),
            bottom=chat_top,
        )

    @classmethod
    def in_virtual_px(
        cls, feet: tuple[float, float], scale: tuple[float, float]
    ) -> Placement:
        """
        A reach at a spot of the map, against mobs placed in virtual px through
        the Camera of the frame they were found on.

        :param scale: That frame's client px per virtual px (`Camera.scale`):
            what one client px of overlap is, in virtual px.
        """
        return cls(feet=feet, scale=scale, units=Units.VIRTUAL)

    def place(self, reach: Reach, side: Side | None) -> Box:
        """
        `reach` in `units`, facing `side`: left for None, as the client stores
        it (a two-sided reach is the same either way), cut at `bottom`.
        """
        box = reach.facing_right() if side == "right" else reach
        fx, fy = self.feet
        sx, sy = self.scale if self.units is Units.CLIENT else (1.0, 1.0)
        bottom = fy + box.rb_y * sy
        if self.bottom is not None:
            bottom = min(bottom, self.bottom)
        return (fx + box.lt_x * sx, fy + box.lt_y * sy, fx + box.rb_x * sx, bottom)

    def touches(self, mob: Box, placed: Box) -> bool:
        """
        Whether the mob's box overlaps the `placed` reach by at least
        `MIN_OVERLAP` client px on each axis: the one rule for "in reach".
        """
        width = min(mob[2], placed[2]) - max(mob[0], placed[0])
        height = min(mob[3], placed[3]) - max(mob[1], placed[1])
        if self.units is Units.VIRTUAL:
            width, height = width * self.scale[0], height * self.scale[1]
        floor = MIN_OVERLAP - _FLOAT_ERROR
        return width >= floor and height >= floor

    def offset(self, mob: Box) -> tuple[int, int, int, int]:
        """The mob's box from the feet, rounded to whole `units`."""
        fx, fy = self.feet
        x1, y1, x2, y2 = mob
        return (round(x1 - fx), round(y1 - fy), round(x2 - fx), round(y2 - fy))

    def distance(self, mob: Box) -> float:
        """How far the mob's box centre is from the feet, horizontally."""
        return abs((mob[0] + mob[2]) / 2 - self.feet[0])


def sides(reach: Reach) -> tuple[Side | None, ...]:
    """
    The sides a cast of `reach` is counted on: None, with no facing, for a
    two-sided reach; left and right for a one-sided one.
    """
    return (None,) if reach.sides is Sides.TWO else SIDES


def in_reach[B: Box](
    reach: Reach, side: Side | None, mobs: Iterable[B], where: Placement
) -> tuple[B, ...]:
    """The mobs whose box is in `reach` placed at `where`, facing `side`."""
    placed = where.place(reach, side)
    return tuple(mob for mob in mobs if where.touches(mob, placed))


def counted[B: Box](
    reach: Reach, mobs: Sequence[B], where: Placement
) -> dict[Side | None, tuple[B, ...]]:
    """
    The mobs in `reach` placed at `where`, by side (`sides`): once, under None,
    for a two-sided reach; facing left and facing right for a one-sided one.
    """
    return {side: in_reach(reach, side, mobs, where) for side in sides(reach)}
