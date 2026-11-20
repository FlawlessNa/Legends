"""
The equipment window, and the weapon it shows (#636).

**The window** is found by its background, `UI/Equipment.img/equip/backgrnd`
(169 x 222), drawn at 1:1. The window shows the character, and the items over
its slots, so most of the background is never exact on a live frame. Only its
border is searched for (`_BORDER` px in from every edge): nothing but a cursor
or a tooltip is drawn over it.

**The weapon.** The weapon slot is `UI/Equipment.img/equip/slots/weapon`, a
`(101, 89)` vector from the window's origin, 32 x 32. Its pixels are compared
with `info/icon` of every weapon that has an afterimage (`Catalogue.weapon_icons`)
by the normalised correlation the buffs use (`buffs.unit_vector`), over the
icon's opaque pixels. An icon is drawn by its origin, which the client places on
the slot's bottom-left corner, so its top-left is `(-origin_x, 32 - origin_y)`
from the slot's. That placement is read from the client's convention, not from a
frame: the comparison tries `_SHIFT` px either way and keeps the best.

The best weapon at or above `WEAPON_MATCH` is the answer; the reader never
guesses below it. Weapons that share one icon (a Wooden Wand and its beginner's
twin) can't be told apart, and the later id is the answer.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from botting.core.errors import StartupRefused
from botting.screen import Frame, Reading, match_best
from game_data.catalogue.catalogue import Catalogue
from game_data.catalogue.model import WeaponData
from game_data.config import CONFIG, STORE
from game_data.sprites import Sprite, SpriteNotFound, Sprites

from .buffs import unit_vector
from .locator import FrameCheck
from .sprites import FRAME_CHECK, Declaration, Profile, load_reader_sprites

_WINDOW = "UI/Equipment.img/equip"
BACKGROUND = f"{_WINDOW}/backgrnd"
WEAPON_SLOT = f"{_WINDOW}/slots/weapon"

EQUIPMENT = Declaration("equipment", canvases=(BACKGROUND,), vectors=(WEAPON_SLOT,))
"""The sprites the equipment reader needs from the store. The weapons' icons are
the catalogue's, and loaded by `load_equipment_reader`."""

SLOT_SIZE = 32

WEAPON_MATCH = 0.5
"""An icon correlating at least this well with the weapon slot is the weapon.
A starting value, not a measurement: it is tuned live (#636), on frames of the
equipment window at the client, which no offline frame can stand in for."""

_BORDER = 4
"""The window's border, in px from each edge, that finds it."""
_BORDER_TOLERANCE = 0.5
"""Mean squared error over the border at which the background is there."""
_SHIFT = 2
"""How far, in px, an icon may sit from where its origin puts it."""


@dataclass(frozen=True, slots=True)
class _Icon:
    weapon: WeaponData
    mask: NDArray[np.bool_]
    vector: NDArray[np.float64]
    left: int
    top: int


class EquipmentReader:
    """
    Finds the equipment window on a frame and reads the weapon it shows.

    :param frame_check: What `read` asks first, as every reader does.
    :param background: The window's background canvas.
    :param slot: The weapon slot's `(x, y)` from the window's origin.
    :param icons: Each candidate weapon, with its icon.
    """

    def __init__(
        self,
        frame_check: FrameCheck,
        background: Sprite,
        slot: tuple[int, int],
        icons: Iterable[tuple[WeaponData, Sprite]],
    ) -> None:
        self._frame_check = frame_check
        self._slot = slot
        rgba = background.rgba.copy()
        height, width = rgba.shape[:2]
        rows, cols = np.indices((height, width))
        edge = (
            (rows < _BORDER)
            | (rows >= height - _BORDER)
            | (cols < _BORDER)
            | (cols >= width - _BORDER)
        )
        rgba[:, :, 3] = np.where(edge & (rgba[:, :, 3] == 255), 255, 0)
        self._border = rgba
        built = [self._icon(w, s) for w, s in icons]
        # An icon with no opaque pixel has nothing to compare.
        self._icons = [icon for icon in built if icon.mask.any()]

    @staticmethod
    def _icon(weapon: WeaponData, sprite: Sprite) -> _Icon:
        rgba = sprite.rgba
        mask = rgba[:, :, 3] == 255
        ox, oy = sprite.origin
        return _Icon(
            weapon,
            mask,
            unit_vector(rgba[:, :, 2::-1][mask]) if mask.any() else np.zeros(0),
            -ox,
            SLOT_SIZE - oy,
        )

    def find_window(self, pixels: NDArray[np.uint8]) -> tuple[int, int] | None:
        """The window's top-left in client pixels, or `None` when it isn't drawn."""
        hit = match_best(pixels, self._border, tolerance=_BORDER_TOLERANCE)
        return None if hit is None else (hit.x, hit.y)

    def read_slot(
        self, pixels: NDArray[np.uint8], window: tuple[int, int]
    ) -> WeaponData | None:
        """The weapon in the slot of the window at `window`, or `None`."""
        slot_x = window[0] + self._slot[0]
        slot_y = window[1] + self._slot[1]
        best, score = None, WEAPON_MATCH
        for icon in self._icons:
            found = self._score(pixels, slot_x, slot_y, icon)
            if found >= score:
                best, score = icon.weapon, found
        return best

    def read(self, frame: Frame) -> Reading[WeaponData]:
        """
        The weapon the window shows. `ABSENT` when the window isn't on the
        frame, and `UNSURE` when it is but no icon matched the slot (it is
        empty, or `WEAPON_MATCH` is too high); the detail says which. Never
        raises because of what is on screen.
        """
        unusable = self._frame_check.frame_usable(frame)
        if unusable is not None:
            return unusable
        window = self.find_window(frame.pixels)
        if window is None:
            return Reading.absent(
                frame.captured_at, "the equipment window wasn't found on the frame"
            )
        weapon = self.read_slot(frame.pixels, window)
        if weapon is None:
            return Reading.unsure(
                frame.captured_at,
                f"the window was found, but no weapon icon matched its weapon slot "
                f"at {WEAPON_MATCH} or more (is the slot empty?)",
            )
        return Reading.read(weapon, frame.captured_at)

    @staticmethod
    def _score(
        pixels: NDArray[np.uint8], slot_x: int, slot_y: int, icon: _Icon
    ) -> float:
        height, width = icon.mask.shape
        best = 0.0
        for dy in range(-_SHIFT, _SHIFT + 1):
            for dx in range(-_SHIFT, _SHIFT + 1):
                x, y = slot_x + icon.left + dx, slot_y + icon.top + dy
                if x < 0 or y < 0:
                    continue
                patch = pixels[y : y + height, x : x + width]
                if patch.shape[:2] != icon.mask.shape:
                    continue
                best = max(best, float(unit_vector(patch[icon.mask]) @ icon.vector))
        return best


def load_equipment_reader(
    root: Path = STORE, *, config: Path = CONFIG
) -> EquipmentReader:
    """
    The equipment reader, from the latest extraction in the store, once the
    store is checked as the other readers' sprites are (`load_reader_sprites`).

    :raises StartupRefused: As `load_reader_sprites` does, or the store has no
        weapon icons.
    """
    sprites = load_reader_sprites(
        [FRAME_CHECK, EQUIPMENT], Profile(job=""), root, config=config
    )
    assert sprites.build is not None
    return equipment_reader(sprites.build, FrameCheck(sprites), root)


def equipment_reader(
    build: str, frame_check: FrameCheck, root: Path = STORE
) -> EquipmentReader:
    """
    The equipment reader of extraction `build`: the window's sprites, and the
    icon of every weapon with an afterimage. The store's freshness isn't
    checked here.

    :raises StartupRefused: A sprite is missing, or the store has no weapon
        icons.
    """
    icons: list[tuple[WeaponData, Sprite]] = []
    with Sprites.open(build, root) as store, Catalogue.open(build, root) as catalogue:
        try:
            background = store.canvas(BACKGROUND)
            slot = store.vector(WEAPON_SLOT)
        except SpriteNotFound as error:
            raise StartupRefused(
                f"the equipment reader needs a sprite build {build} doesn't "
                f"have: {error}. If the client was patched, run "
                "`python -m game_data extract`"
            ) from error
        for row in catalogue.weapon_icons():
            if row.image is None:
                continue
            weapon = catalogue.weapon(row.weapon)
            if weapon.afterimage is None:
                continue
            rgba = store.store.images.read(row.image)
            icons.append(
                (weapon, Sprite(row.image, rgba, (row.origin_x, row.origin_y)))
            )
    if not icons:
        raise StartupRefused(
            f"the game data store {root} holds no weapon icons: run "
            "`python -m game_data extract`"
        )
    return EquipmentReader(frame_check, background, slot, icons)


__all__ = [
    "BACKGROUND",
    "EQUIPMENT",
    "WEAPON_MATCH",
    "WEAPON_SLOT",
    "EquipmentReader",
    "equipment_reader",
    "load_equipment_reader",
]
