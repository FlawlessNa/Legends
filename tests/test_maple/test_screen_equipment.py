"""
The equipment reader, on synthetic frames: noise stands for the window's
background and the weapon icons, which the test draws itself. Nothing here is
client pixels; the client's own are in `test_screen_equipment_client_files`.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.catalogue.model import WeaponData
from game_data.sprites import Sprite
from maple.screen.equipment import SLOT_SIZE, EquipmentReader
from maple.screen.locator import FrameCheck
from maple.screen.sprites import GAUGE_LABEL, ReaderSprites
from tests.test_maple import test_screen_minimap as minimap

RNG = np.random.default_rng(636)
WIDTH, HEIGHT = 500, 320
WINDOW = (140, 30)
SLOT = (101, 89)
ORIGIN = (0, 31)


def _noise(height: int, width: int, *, solid: bool = True) -> np.ndarray:
    rgba = np.zeros((height, width, 4), np.uint8)
    rgba[:, :, :3] = RNG.integers(0, 256, (height, width, 3), dtype=np.uint8)
    rgba[:, :, 3] = 255
    if not solid:
        rgba[:3, :3, 3] = 0
    return rgba


BACKGROUND = Sprite("background", _noise(222, 169, solid=False), (0, 0))
ICONS = {
    weapon_id: Sprite(f"icon {weapon_id}", _noise(30, 28), ORIGIN)
    for weapon_id in (1302000, 1402000, 1432000)
}
WEAPONS = {
    weapon_id: WeaponData(weapon_id, f"W{weapon_id}", "swordOL", 4, 1)
    for weapon_id in ICONS
}


@pytest.fixture
def reader() -> EquipmentReader:
    sprites = ReaderSprites("build", {GAUGE_LABEL: minimap.SPRITES[GAUGE_LABEL]})
    return EquipmentReader(
        FrameCheck(sprites),
        BACKGROUND,
        SLOT,
        [(WEAPONS[i], icon) for i, icon in ICONS.items()],
    )


def _draw(pixels: np.ndarray, rgba: np.ndarray, x: int, y: int) -> None:
    keep = rgba[:, :, 3] == 255
    h, w = rgba.shape[:2]
    pixels[y : y + h, x : x + w][keep] = rgba[:, :, 2::-1][keep]


def window_frame(
    weapon: int | None, *, window: bool = True, ok: bool = True, shift: int = 0
) -> Frame:
    """A frame of the window, with `weapon` in its slot."""
    pixels = np.full((HEIGHT, WIDTH, 3), 40, np.uint8)
    minimap.paste(pixels, minimap.SPRITES[GAUGE_LABEL], 10, HEIGHT - 12)
    if window:
        _draw(pixels, BACKGROUND.rgba, *WINDOW)
    if weapon is not None:
        _draw(
            pixels,
            ICONS[weapon].rgba,
            WINDOW[0] + SLOT[0] - ORIGIN[0] + shift,
            WINDOW[1] + SLOT[1] + SLOT_SIZE - ORIGIN[1] + shift,
        )
    return Frame(pixels, (WIDTH, HEIGHT), 7.0, True, ok, "" if ok else "moved")


@pytest.mark.parametrize("weapon", list(ICONS))
def test_the_weapon_in_the_slot_is_named(reader: EquipmentReader, weapon: int) -> None:
    reading = reader.read(window_frame(weapon))

    assert reading.status is Status.READ
    assert reading.value == WEAPONS[weapon]


def test_an_icon_a_pixel_off_where_its_origin_puts_it_is_still_named(
    reader: EquipmentReader,
) -> None:
    reading = reader.read(window_frame(1402000, shift=1))

    assert reading.value == WEAPONS[1402000]


def test_the_window_is_found_where_it_is_drawn(reader: EquipmentReader) -> None:
    assert reader.find_window(window_frame(None).pixels) == WINDOW


def test_items_over_the_window_do_not_hide_it(reader: EquipmentReader) -> None:
    frame = window_frame(1302000)
    x, y = WINDOW
    frame.pixels[y + 30 : y + 180, x + 15 : x + 155] = 200

    assert reader.find_window(frame.pixels) == WINDOW


def test_no_window_is_absent_with_no_value(reader: EquipmentReader) -> None:
    reading = reader.read(window_frame(1302000, window=False))

    assert reading.status is Status.ABSENT
    assert reading.value is None


def test_an_empty_slot_is_unsure_with_no_value(reader: EquipmentReader) -> None:
    reading = reader.read(window_frame(None))

    assert reading.status is Status.UNSURE
    assert reading.value is None
    assert "no weapon icon matched" in reading.detail


def test_an_unusable_frame_is_unsure(reader: EquipmentReader) -> None:
    reading = reader.read(window_frame(1302000, ok=False))

    assert reading.status is Status.UNSURE
    assert reading.value is None
