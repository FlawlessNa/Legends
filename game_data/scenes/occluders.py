"""
Occluders: what the client draws over mobs, laid out as `Overlay`s for
`draw_mobs` to draw and count against each mob's `visible`.

Each kind is configured per map, because what a map shows differs: the
client holds no drop tables (drops are the server's), and the damage players
deal depends on their level.

- **Drops** (`Drops`) come from the map's `pool`: `meso:<id>` and
  `item:<id>` keys, each with a weight. A meso is drawn at a frame of its spin
  drawn uniformly; an item as its icon. Either is laid out as in an inventory
  slot of `DROP_SLOT` pixels, centred on its `x` with its bottom on the
  ground, which is where its `origin` puts it. Where drops lie is
  `compose_scene`'s: at kill sites, `sites_per_mob` per mob in view, each of
  `per_site` drops `spread` pixels apart, each `DROP_JITTER` pixels at most
  off its place.
- **Damage numbers** (`Damage`) are above the head of a mob with a pixel in
  the view: its frame's `head` when it has one, else the middle of its opaque
  pixels' top. A number's bottom is raised 0 to `DAMAGE_RISE` pixels above
  that, and it is centred on it. Its value is drawn in `values`, its digits
  from one of `sets`: a set `<stem><2k>` draws every digit but the first,
  which its partner `<stem><2k + 1>` draws larger. Digits overlap by
  `DIGIT_OVERLAP` pixels. Numbers are always in front.

The layout constants are first guesses, to be judged by eye against real
screens.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import numpy as np

from game_data.archive import Pixels
from game_data.catalogue import Catalogue
from game_data.render import Images

DROP_SLOT: Final = 32
DROP_JITTER: Final = 3
"""The most a drop strays from its place in a kill site's fan, in pixels."""

DAMAGE_SETS: Final = ("NoRed0", "NoCri0")
"""
The client's default digit sets of damage dealt to a mob, a normal hit and a
critical one, with their partners `NoRed1` and `NoCri1`. The others (`NoRed2`,
`NoCri2`...) are skins.
"""

DAMAGE_RISE: Final = 60
DIGIT_OVERLAP: Final = 8


def check_range(name: str, value: Sequence[float]) -> None:
    """
    :raises ValueError: `value` isn't `(min, max)` with `0 <= min <= max`.
    """
    if len(value) != 2 or not 0 <= value[0] <= value[1]:
        raise ValueError(
            f"{name} must be (min, max) with 0 <= min <= max, not {tuple(value)}"
        )


@dataclass(frozen=True, slots=True)
class Drops:
    """
    A map's drops.

    :ivar pool: What drops, by `meso:<id>` or `item:<id>`, each with its
        weight. The weights needn't add up to 1.
    :ivar sites_per_mob: The fewest and most kill sites per mob with a pixel
        in the view; their number is that times the mobs, rounded.
    :ivar per_site: The fewest and most drops at one kill site.
    :ivar spread: How far apart a site's drops lie, in pixels.
    :raises ValueError: The pool is empty, a key isn't `meso:<id>` or
        `item:<id>`, a weight isn't positive, a range is out of order, or
        `spread` is negative.
    """

    pool: Mapping[str, float]
    sites_per_mob: tuple[float, float] = (0.0, 0.8)
    per_site: tuple[int, int] = (1, 3)
    spread: int = 24

    def __post_init__(self) -> None:
        if not self.pool:
            raise ValueError("a drop pool needs at least one drop")
        for key, weight in self.pool.items():
            kind, _, ident = key.partition(":")
            if kind not in ("meso", "item") or not ident.isdigit():
                raise ValueError(f"a drop is 'meso:<id>' or 'item:<id>', not {key!r}")
            if not weight > 0:
                raise ValueError(f"drop {key!r} must weigh more than 0, not {weight}")
        check_range("drops' sites_per_mob", self.sites_per_mob)
        check_range("drops' per_site", self.per_site)
        if self.spread < 0:
            raise ValueError(f"drops' spread can't be negative, not {self.spread}")


@dataclass(frozen=True, slots=True)
class Damage:
    """
    A map's damage numbers.

    :ivar count: The fewest and most numbers per scene.
    :ivar values: The smallest and largest number drawn.
    :ivar sets: The digit sets drawn among, each `<stem><2k>`, its larger
        first digits being `<stem><2k + 1>`.
    :raises ValueError: A range is out of order, `values` starts under 1, or
        `sets` is empty.
    """

    count: tuple[int, int] = (0, 3)
    values: tuple[int, int] = (1, 9999)
    sets: tuple[str, ...] = DAMAGE_SETS

    def __post_init__(self) -> None:
        check_range("damage's count", self.count)
        check_range("damage's values", self.values)
        if self.values[0] < 1:
            raise ValueError(
                f"damage's values must start at 1 or more, not {self.values}"
            )
        if not self.sets:
            raise ValueError("damage needs at least one digit set")


@dataclass(frozen=True, slots=True)
class Overlay:
    """RGBA `pixels` to draw over the view, their top left at `(left, top)`."""

    pixels: Pixels
    left: int
    top: int


@dataclass(frozen=True, slots=True)
class Sprite:
    """An occluder's frame: its image's hash and its origin."""

    image: str
    origin: tuple[int, int]


type Digits = dict[int, Sprite]
"""A digit set, by digit."""

type Pool = list[tuple[list[Sprite], float]]
"""A drop pool resolved to sprites: each drop's frames, with its weight."""

type Pairs = list[tuple[Digits, Digits]]
"""Digit sets resolved to sprites: each `(rest, first)`."""


@dataclass(slots=True)
class Sprites:
    """
    The catalogue's occluder sprites that have an image.

    :ivar items: Each item's icon, by item ID.
    :ivar mesos: Each meso sprite's frames, by its ID.
    :ivar digits: Each digit set with all ten digits, by name.
    """

    items: dict[int, Sprite] = field(default_factory=dict[int, Sprite])
    mesos: dict[int, list[Sprite]] = field(default_factory=dict[int, list[Sprite]])
    digits: dict[str, Digits] = field(default_factory=dict[str, Digits])

    @classmethod
    def read(cls, cat: Catalogue) -> Sprites:
        found = cls()
        found.items = {
            icon.item: Sprite(icon.image, (icon.origin_x, icon.origin_y))
            for icon in cat.item_icons()
            if icon.image is not None
        }
        for frame in cat.meso_frames():
            if frame.image is not None:
                found.mesos.setdefault(frame.meso, []).append(
                    Sprite(frame.image, (frame.origin_x, frame.origin_y))
                )
        sets: dict[str, Digits] = {}
        for digit in cat.damage_digits():
            if digit.image is not None:
                sets.setdefault(digit.digit_set, {})[digit.digit] = Sprite(
                    digit.image, (digit.origin_x, digit.origin_y)
                )
        found.digits = {name: d for name, d in sets.items() if len(d) == 10}
        return found

    def pool(self, drops: Drops) -> Pool:
        """
        The pool's sprites and weights, in its order: a meso's frames, or an
        item's icon alone.

        :raises ValueError: The catalogue has no sprite for a drop, naming the
            first.
        """
        found: Pool = []
        for key, weight in drops.pool.items():
            kind, _, ident = key.partition(":")
            if kind == "meso":
                frames = self.mesos.get(int(ident), [])
            else:
                icon = self.items.get(int(ident))
                frames = [] if icon is None else [icon]
            if not frames:
                raise ValueError(f"the catalogue has no sprite for drop {key!r}")
            found.append((frames, weight))
        return found

    def pairs(self, damage: Damage) -> Pairs:
        """
        Each of the damage's sets with its partner, `(rest, first)`.

        :raises ValueError: A set isn't named `<stem><even number>`, or it or
            its partner isn't in the catalogue with all ten digits.
        """
        found: Pairs = []
        for name in damage.sets:
            stem = name.rstrip("0123456789")
            number = name[len(stem) :]
            if not stem or not number or int(number) % 2:
                raise ValueError(
                    "a damage set is named <stem><even number>, such as NoRed0, "
                    f"not {name!r}"
                )
            partner = f"{stem}{int(number) + 1}"
            for needed in (name, partner):
                if needed not in self.digits:
                    raise ValueError(
                        f"the catalogue has no digit set {needed!r} with all ten digits"
                    )
            found.append((self.digits[name], self.digits[partner]))
        return found


def drop(
    pool: Pool, images: Images, x: int, y: int, rng: np.random.Generator
) -> Overlay:
    """One drop of the `pool` on the ground at view pixel `(x, y)`."""
    weights = np.array([weight for _, weight in pool], dtype=float)
    frames = pool[int(rng.choice(len(pool), p=weights / weights.sum()))][0]
    sprite = frames[int(rng.integers(len(frames)))]
    origin_x, origin_y = sprite.origin
    return Overlay(
        images.get(sprite.image), x - DROP_SLOT // 2 - origin_x, y - origin_y
    )


def damage(
    pairs: Pairs,
    values: tuple[int, int],
    images: Images,
    x: int,
    y: int,
    rng: np.random.Generator,
) -> list[Overlay]:
    """
    A damage number above view pixel `(x, y)`, its value drawn in `values`,
    its digits from one of the `pairs`: one overlay per digit, left to right.
    """
    rest, first = pairs[int(rng.integers(len(pairs)))]
    digits = [int(d) for d in str(int(rng.integers(values[0], values[1] + 1)))]
    bottom = y - int(rng.integers(DAMAGE_RISE + 1))
    drawn = [
        (images.get(sprite.image), sprite.origin)
        for sprite in (
            (first if n == 0 else rest)[digit] for n, digit in enumerate(digits)
        )
    ]
    widths = [pixels.shape[1] for pixels, _ in drawn]
    left = x - (sum(widths) - DIGIT_OVERLAP * (len(digits) - 1)) // 2
    overlays: list[Overlay] = []
    for (pixels, (_, origin_y)), width in zip(drawn, widths, strict=True):
        overlays.append(Overlay(pixels, left, bottom - origin_y))
        left += width - DIGIT_OVERLAP
    return overlays


def head(
    pixels: Pixels, left: int, top: int, head_at: Sequence[int] | None
) -> tuple[int, int]:
    """
    Where a mob's head is in the view: `head_at` when its frame has one, else
    the middle of the top of its sprite's opaque pixels, drawn at
    `(left, top)`; the sprite's top middle when none is opaque.
    """
    if head_at is not None:
        return head_at[0], head_at[1]
    opaque = pixels[..., 3] > 0
    rows = np.flatnonzero(opaque.any(axis=1))
    columns = np.flatnonzero(opaque.any(axis=0))
    if not len(rows):
        return left + pixels.shape[1] // 2, top
    return left + (int(columns[0]) + int(columns[-1]) + 1) // 2, top + int(rows[0])
