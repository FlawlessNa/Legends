"""
The equipment reader on the client's own sprites, from the latest extraction in
the store (`python -m game_data extract`). Marked `client_files`; run with
`pytest -m client_files`.

Frames are composed: the window's background drawn at an offset over a plain
background, and a weapon's icon in its slot, placed by its origin on the slot's
bottom-left corner. That placement is the reader's own assumption, so these
tests cannot say that the client draws it so; only a live frame can.
"""

import numpy as np
import pytest

from botting.screen import Frame, Status
from game_data.catalogue import Catalogue
from game_data.config import STORE
from game_data.sprites import Sprites
from maple.screen.equipment import (
    BACKGROUND,
    SLOT_SIZE,
    WEAPON_SLOT,
    EquipmentReader,
    equipment_reader,
)
from maple.screen.locator import FrameCheck
from maple.screen.sprites import GAUGE_LABEL, ReaderSprites

pytestmark = pytest.mark.client_files

SIZE = (800, 600)
OFFSET = (231, 87)
WEAPONS = (1302000, 1402000, 1432000, 1442000)


@pytest.fixture(scope="module")
def reader() -> EquipmentReader:
    with Sprites.latest(STORE) as sprites:
        check = FrameCheck(
            ReaderSprites(sprites.build, {GAUGE_LABEL: sprites.canvas(GAUGE_LABEL)})
        )
        return equipment_reader(sprites.build, check, STORE)


def _blend(
    frame: np.ndarray, rgba: np.ndarray, x: int, y: int, *, solid: bool = False
) -> None:
    height, width = rgba.shape[:2]
    drawn = rgba[:, :, 3] == 255 if not solid else rgba[:, :, 3] > 0
    area = frame[y : y + height, x : x + width]
    area[drawn] = rgba[:, :, 2::-1][drawn]


def _frame(weapon: int | None, *, window: bool = True) -> Frame:
    frame = np.full((SIZE[1], SIZE[0], 3), (60, 70, 80), np.uint8)
    with Sprites.latest(STORE) as sprites, Catalogue.latest(STORE) as catalogue:
        label = sprites.canvas(GAUGE_LABEL)
        _blend(frame, label.rgba, 10, SIZE[1] - 30)
        if window:
            _blend(frame, sprites.canvas(BACKGROUND).rgba, *OFFSET)
        if weapon is not None:
            icon = next(i for i in catalogue.weapon_icons() if i.weapon == weapon)
            assert icon.image is not None
            slot_x, slot_y = sprites.vector(WEAPON_SLOT)
            _blend(
                frame,
                sprites.store.images.read(icon.image),
                OFFSET[0] + slot_x - icon.origin_x,
                OFFSET[1] + slot_y + SLOT_SIZE - icon.origin_y,
            )
    return Frame(frame, SIZE, 7.0, True, True)


@pytest.mark.parametrize("weapon", WEAPONS)
def test_the_reader_names_the_weapon_in_the_slot(
    reader: EquipmentReader, weapon: int
) -> None:
    reading = reader.read(_frame(weapon))

    assert reading.value is not None
    assert reading.value.id == weapon


def test_the_window_is_found_where_it_is_drawn(reader: EquipmentReader) -> None:
    assert reader.find_window(_frame(None).pixels) == OFFSET


def test_items_and_the_character_over_the_window_do_not_hide_it(
    reader: EquipmentReader,
) -> None:
    frame = _frame(WEAPONS[0]).pixels
    x, y = OFFSET
    noise = np.random.default_rng(636).integers(0, 256, (150, 140, 3), np.uint8)
    frame[y + 30 : y + 180, x + 15 : x + 155] = noise
    frame[y + 89 : y + 121, x + 101 : x + 133] = _frame(WEAPONS[0]).pixels[
        y + 89 : y + 121, x + 101 : x + 133
    ]

    assert reader.find_window(frame) == OFFSET


def test_no_window_reads_nothing(reader: EquipmentReader) -> None:
    frame = _frame(WEAPONS[0], window=False)

    assert reader.find_window(frame.pixels) is None
    reading = reader.read(frame)
    assert reading.status is Status.ABSENT
    assert reading.value is None


def test_an_empty_slot_reads_nothing(reader: EquipmentReader) -> None:
    frame = _frame(None)

    assert reader.find_window(frame.pixels) == OFFSET
    reading = reader.read(frame)
    assert reading.status is Status.UNSURE
    assert reading.value is None
