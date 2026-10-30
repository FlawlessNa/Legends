"""
Occluders: what the client draws over mobs, laid out as `Overlay`s for
`draw_mobs` to draw and count against each mob's `visible`.

- **Drops** lie on a mob spawn's foothold, `x` uniform in its `[rx0, rx1]`.
  Each is a meso, a `MESO_SHARE` of the time, at a frame of its spin drawn
  uniformly; or an item's icon, drawn uniformly among the items of
  `DROP_CATEGORIES`. An icon is laid out as in an inventory slot of
  `DROP_SLOT` pixels, centred on `x` with its bottom on the ground, which is
  where its `origin` puts it. Each drop is behind or in front of the mobs at
  random.
- **Damage numbers** are above the head of a mob with a pixel in the view:
  its frame's `head` when it has one, else the middle of its opaque pixels'
  top. A number's bottom is
  raised 0 to `DAMAGE_RISE` pixels above that, and it is centred on it. It
  has 1 to `DAMAGE_DIGITS` digits, its first never 0, drawn from a pair of
  digit sets of one of `DAMAGE_SETS`: `<set><2k + 1>` for its first digit,
  the larger, and `<set><2k>` for the rest. Digits overlap by
  `DIGIT_OVERLAP` pixels. Numbers are always in front.

The constants are first guesses, to be judged by eye against real screens.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

import numpy as np

from game_data.archive import Pixels
from game_data.catalogue import Catalogue
from game_data.render import Images

KINDS: Final = ("drops", "damage")
"""The occluders `compose_scene` can draw, each turned on by a count range."""

DROP_CATEGORIES: Final = ("Consume", "Etc", "Install")
"""The item categories drops are drawn among: those mobs drop. Not `Cash`."""

MESO_SHARE: Final = 0.5
DROP_SLOT: Final = 32

DAMAGE_SETS: Final = ("NoRed", "NoCri")
"""The digit sets of damage dealt to a mob: a normal hit and a critical one."""

DAMAGE_DIGITS: Final = 6
DAMAGE_RISE: Final = 60
DIGIT_OVERLAP: Final = 8


@dataclass(frozen=True, slots=True)
class Overlay:
    """RGBA `pixels` to draw over the view, their top left at `(left, top)`."""

    pixels: Pixels
    left: int
    top: int


@dataclass(frozen=True, slots=True)
class _Sprite:
    image: str
    origin: tuple[int, int]


@dataclass(slots=True)
class Sprites:
    """
    The catalogue's occluder sprites that have an image.

    :ivar items: The icons of `DROP_CATEGORIES`' items.
    :ivar mesos: Each meso sprite's frames.
    :ivar digits: Each pair of digit sets, `(rest, first)`, each by digit.
    """

    items: list[_Sprite] = field(default_factory=list[_Sprite])
    mesos: list[list[_Sprite]] = field(default_factory=list[list[_Sprite]])
    digits: list[tuple[dict[int, _Sprite], dict[int, _Sprite]]] = field(
        default_factory=list[tuple[dict[int, _Sprite], dict[int, _Sprite]]]
    )

    @classmethod
    def read(cls, cat: Catalogue) -> Sprites:
        found = cls()
        found.items = [
            _Sprite(icon.image, (icon.origin_x, icon.origin_y))
            for icon in cat.item_icons()
            if icon.category in DROP_CATEGORIES and icon.image is not None
        ]
        mesos: dict[int, list[_Sprite]] = {}
        for frame in cat.meso_frames():
            if frame.image is not None:
                mesos.setdefault(frame.meso, []).append(
                    _Sprite(frame.image, (frame.origin_x, frame.origin_y))
                )
        found.mesos = list(mesos.values())
        sets: dict[str, dict[int, _Sprite]] = {}
        for digit in cat.damage_digits():
            if digit.image is not None:
                sets.setdefault(digit.digit_set, {})[digit.digit] = _Sprite(
                    digit.image, (digit.origin_x, digit.origin_y)
                )
        whole = {name: digits for name, digits in sets.items() if len(digits) == 10}
        for stem in DAMAGE_SETS:
            for pair in range(len(whole)):
                rest = whole.get(f"{stem}{2 * pair}")
                first = whole.get(f"{stem}{2 * pair + 1}")
                if rest is not None and first is not None:
                    found.digits.append((rest, first))
        return found

    def has(self, kind: str) -> bool:
        """Whether there is anything to draw of `kind`."""
        return bool(self.items or self.mesos) if kind == "drops" else bool(self.digits)


def check(occluders: Mapping[str, tuple[int, int]]) -> None:
    """
    :raises ValueError: A kind isn't one of `KINDS`, or its range isn't
        `0 <= min <= max`.
    """
    for kind, (low, high) in occluders.items():
        if kind not in KINDS:
            raise ValueError(
                f"no occluder {kind!r}; the occluders are {', '.join(KINDS)}"
            )
        if not 0 <= low <= high:
            raise ValueError(
                f"occluders[{kind!r}] must be (min, max) with 0 <= min <= max, not "
                f"{(low, high)}"
            )


def drop(
    sprites: Sprites, images: Images, x: int, y: int, rng: np.random.Generator
) -> Overlay:
    """A drop on the ground at view pixel `(x, y)`; `sprites` has one."""
    meso = bool(sprites.mesos) and (
        not sprites.items or bool(rng.random() < MESO_SHARE)
    )
    if meso:
        frames = sprites.mesos[int(rng.integers(len(sprites.mesos)))]
        sprite = frames[int(rng.integers(len(frames)))]
    else:
        sprite = sprites.items[int(rng.integers(len(sprites.items)))]
    origin_x, origin_y = sprite.origin
    return Overlay(
        images.get(sprite.image), x - DROP_SLOT // 2 - origin_x, y - origin_y
    )


def damage(
    sprites: Sprites, images: Images, x: int, y: int, rng: np.random.Generator
) -> list[Overlay]:
    """
    A damage number above view pixel `(x, y)`, one overlay per digit, left to
    right; `sprites` has digits.
    """
    rest, first = sprites.digits[int(rng.integers(len(sprites.digits)))]
    count = int(rng.integers(1, DAMAGE_DIGITS + 1))
    digits = [
        int(rng.integers(1, 10)),
        *(int(d) for d in rng.integers(10, size=count - 1)),
    ]
    bottom = y - int(rng.integers(DAMAGE_RISE + 1))
    drawn = [
        (images.get(sprite.image), sprite.origin)
        for sprite in (
            (first if n == 0 else rest)[digit] for n, digit in enumerate(digits)
        )
    ]
    widths = [pixels.shape[1] for pixels, _ in drawn]
    left = x - (sum(widths) - DIGIT_OVERLAP * (count - 1)) // 2
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
