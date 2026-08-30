import cv2
import os
import numpy as np
import re

from types import SimpleNamespace

import pytest

from botting.utilities import (
    Box,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
)
from paths import ROOT
from maple.model.interface import Minimap


class MinimapTester(Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


@pytest.fixture(scope="module")
def mm() -> SimpleNamespace:
    """
    The reference data every test compares against, built once for the module.

    Returns a namespace rather than loose fixtures because the expectations are
    derived from one another: the corrected character positions are offsets into the
    map-area boxes, which are themselves offsets into the world-icon boxes.
    """
    dummy_handle = 0
    minimap = MinimapTester()  # This allows us to create a Minimap instance
    images = [
        img
        for img in os.listdir(os.path.join(ROOT, "tests/images"))
        if img.startswith("test_minimap")
    ]
    images.sort(key=lambda x: eval(re.search(r"\d+", x).group()))
    test_images = {img: cv2.imread(f"images/{img}") for img in images}
    _is_displayed = [
        True,
        True,
        False,
        False,
        True,
        True,
        True,
        True,
        True,
        False,
        True,
        True,
        True,
        True,
    ]
    _minimap_state = [
        "Full",
        "Full",
        "Hidden",
        "Hidden",
        "Partial",
        "Partial",
        "Partial",
        "Partial",
        "Full",
        "Hidden",
        "Partial",
        "Full",
        "Partial",
        "Full",
    ]
    # Defined by looking at pixel positions with Paint
    _world_icons_top_left = [
        (105, 30),
        (517, 186),
        (625, 184),
        (488, 279),
        (362, 281),
        (791, 406),
        (830, 97),
        (871, 97),
        (408, 126),
        (780, 445),
        (248, 86),
        (701, 77),
        (417, 171),
        (568, 247),
    ]
    # Defined by looking at pixel positions with Paint
    _world_icons_bot_right = [
        (138, 39),
        (550, 195),
        (658, 193),
        (521, 288),
        (395, 290),
        (824, 415),
        (863, 106),
        (904, 106),
        (441, 135),
        (813, 454),
        (281, 95),
        (734, 86),
        (450, 180),
        (601, 256),
    ]
    _world_icons_box = [
        Box(
            left=_world_icons_top_left[i][0] + CLIENT_HORIZONTAL_MARGIN_PX,
            right=_world_icons_bot_right[i][0] + CLIENT_HORIZONTAL_MARGIN_PX + 1,
            top=_world_icons_top_left[i][1] + CLIENT_VERTICAL_MARGIN_PX,
            bottom=_world_icons_bot_right[i][1] + CLIENT_VERTICAL_MARGIN_PX + 1,
        )
        for i in range(len(_world_icons_top_left))
    ]
    # Defined by looking at pixel positions with Paint
    _map_area_top_left = [
        (6, 95),
        (418, 251),
        None,
        None,
        (281, 303),
        (710, 428),
        (749, 119),
        (749, 119),
        (276, 191),
        None,
        (126, 108),
        (569, 142),
        (258, 193),
        (406, 312),
    ]
    # Defined by looking at pixel positions with Paint
    _map_area_bot_right = [
        (139, 151),
        (551, 307),
        None,
        None,
        (396, 359),
        (825, 484),
        (864, 175),
        (905, 209),
        (442, 281),
        None,
        (282, 198),
        (735, 232),
        (451, 247),
        (602, 366),
    ]
    # Only applicable when minimap is fully displayed.
    _extra_widths = [18, 18, None, None, 0, 0, 0, 0, 10, None, 0, 10, 0, [1, 2]]
    _map_area_box = [
        (
            Box(
                left=_map_area_top_left[i][0]
                + CLIENT_HORIZONTAL_MARGIN_PX
                + [
                    (
                        _extra_widths[i] // 2
                        if isinstance(_extra_widths[i], int)
                        else _extra_widths[i][0]
                    )
                ].pop(),
                right=_map_area_bot_right[i][0]
                + CLIENT_HORIZONTAL_MARGIN_PX
                + 1
                - [
                    (
                        _extra_widths[i] // 2
                        if isinstance(_extra_widths[i], int)
                        else _extra_widths[i][1]
                    )
                ].pop(),
                top=_map_area_top_left[i][1] + CLIENT_VERTICAL_MARGIN_PX,
                bottom=_map_area_bot_right[i][1] + CLIENT_VERTICAL_MARGIN_PX + 1,
            )
            if _map_area_top_left[i] is not None
            else None
        )
        for i in range(len(_world_icons_top_left))
    ]
    # Defined by looking at pixel positions with Paint
    _entire_minimap_top_left = [
        (6, 30),
        (418, 186),
        None,
        None,
        (281, 281),
        (710, 406),
        (749, 97),
        (749, 97),
        (276, 126),
        None,
        (126, 86),
        (569, 77),
        (258, 171),
        (406, 247),
    ]
    _entire_minimap_box = [
        (
            Box(
                left=_entire_minimap_top_left[i][0] + CLIENT_HORIZONTAL_MARGIN_PX,
                right=_map_area_bot_right[i][0] + CLIENT_HORIZONTAL_MARGIN_PX + 1,
                top=_entire_minimap_top_left[i][1] + CLIENT_VERTICAL_MARGIN_PX,
                bottom=_map_area_bot_right[i][1] + CLIENT_VERTICAL_MARGIN_PX + 1,
            )
            if _map_area_top_left[i] is not None
            else None
        )
        for i in range(len(_world_icons_top_left))
    ]

    _self_position = [
        [(108, 133)],
        [(518, 289)],
        None,
        None,
        [(363, 341)],
        [(789, 466)],
        [(831, 157)],
        [(842, 172)],
        [(374, 244)],
        None,
        [(226, 161)],
        [(683, 195)],
        [(397, 228)],
        [(579, 347)],
    ]
    _stranger_position = [
        [],
        [],
        None,
        None,
        [],
        [],
        [],
        [(809, 158), (813, 191), (818, 191), (831, 189)],
        [(341, 230), (345, 263), (350, 263), (363, 261)],
        None,
        [(186, 147), (190, 180), (195, 180), (208, 178)],
        [(634, 181), (638, 214), (643, 214), (656, 212)],
        [],
        [],
    ]
    _npc_position = [
        [],
        [],
        None,
        None,
        [],
        [],
        [],
        [(757, 191), (767, 174), (780, 176), (788, 176)],
        [(289, 263), (299, 246), (312, 248), (320, 248)],
        None,
        [(134, 180), (144, 163), (157, 165), (165, 165)],
        [(582, 214), (592, 197), (605, 199), (613, 199)],
        [],
        [],
    ]
    _corrected_self_position = []
    _corrected_stranger_position = []
    _corrected_npc_position = []
    for i, position in enumerate(_self_position):
        if position is None:
            _corrected_self_position.append(None)
        else:
            _corrected_self_position.append(
                [
                    (
                        pos[0] - _map_area_box[i].left + CLIENT_HORIZONTAL_MARGIN_PX,
                        pos[1] - _map_area_box[i].top + CLIENT_VERTICAL_MARGIN_PX,
                    )
                    for pos in position
                ]
            )
    for i, position in enumerate(_stranger_position):
        if position is None:
            _corrected_stranger_position.append(None)
        else:
            _corrected_stranger_position.append(
                [
                    (
                        pos[0] - _map_area_box[i].left + CLIENT_HORIZONTAL_MARGIN_PX,
                        pos[1] - _map_area_box[i].top + CLIENT_VERTICAL_MARGIN_PX,
                    )
                    for pos in position
                ]
            )
    for i, position in enumerate(_npc_position):
        if position is None:
            _corrected_npc_position.append(None)
        else:
            _corrected_npc_position.append(
                [
                    (
                        pos[0] - _map_area_box[i].left + CLIENT_HORIZONTAL_MARGIN_PX,
                        pos[1] - _map_area_box[i].top + CLIENT_VERTICAL_MARGIN_PX - 1,
                    )
                    for pos in position
                ]
            )

    _buddy_position = NotImplemented
    _guildie_position = NotImplemented
    _party_position = NotImplemented

    return SimpleNamespace(
        dummy_handle=dummy_handle,
        minimap=minimap,
        test_images=test_images,
        is_displayed=_is_displayed,
        minimap_state=_minimap_state,
        world_icons_box=_world_icons_box,
        map_area_box=_map_area_box,
        entire_minimap_box=_entire_minimap_box,
        self_position=_corrected_self_position,
        stranger_position=_corrected_stranger_position,
        npc_position=_corrected_npc_position,
    )


def test_is_displayed(mm):
    """
    We test the function with both the image provided and/or the world icon detection box provided.
    :return:
    """
    for idx, img in enumerate(mm.test_images):
        assert (
            mm.minimap.is_displayed(mm.dummy_handle, mm.test_images[img], None)
            == mm.is_displayed[idx]
        )
        assert (
            mm.minimap.is_displayed(
                mm.dummy_handle, mm.test_images[img], mm.world_icons_box[idx]
            )
            == mm.is_displayed[idx]
        )


def test_get_minimap_state(mm):
    for idx, img in enumerate(mm.test_images):
        assert (
            mm.minimap.get_minimap_state(mm.dummy_handle, mm.test_images[img], None)
            == mm.minimap_state[idx]
        )
        assert (
            mm.minimap.get_minimap_state(
                mm.dummy_handle, mm.test_images[img], mm.world_icons_box[idx]
            )
            == mm.minimap_state[idx]
        )


def test_get_character_positions(mm):
    """
    TODO - Test with "Party" members as well as "Guild" members and "Buddies".
    """

    def _single_test(expected, *params):
        actual = mm.minimap.get_character_positions(*params)
        if expected is None:
            assert actual is None
            return
        assert set(actual) == set(expected)

    for idx, img in enumerate(mm.test_images):
        _single_test(mm.self_position[idx], 0, "Self", mm.test_images[img], None, None)
        _single_test(
            mm.self_position[idx],
            0,
            "Self",
            mm.test_images[img],
            mm.world_icons_box[idx],
            None,
        )
        _single_test(
            mm.self_position[idx],
            0,
            "Self",
            mm.test_images[img],
            None,
            mm.map_area_box[idx],
        )
        _single_test(
            mm.self_position[idx],
            0,
            "Self",
            mm.test_images[img],
            mm.world_icons_box[idx],
            mm.map_area_box[idx],
        )

        _single_test(
            mm.stranger_position[idx], 0, "Stranger", mm.test_images[img], None, None
        )
        _single_test(
            mm.stranger_position[idx],
            0,
            "Stranger",
            mm.test_images[img],
            mm.world_icons_box[idx],
            None,
        )
        _single_test(
            mm.stranger_position[idx],
            0,
            "Stranger",
            mm.test_images[img],
            None,
            mm.map_area_box[idx],
        )
        _single_test(
            mm.stranger_position[idx],
            0,
            "Stranger",
            mm.test_images[img],
            mm.world_icons_box[idx],
            mm.map_area_box[idx],
        )

        _single_test(mm.npc_position[idx], 0, "NPC", mm.test_images[img], None, None)
        _single_test(
            mm.npc_position[idx],
            0,
            "NPC",
            mm.test_images[img],
            mm.world_icons_box[idx],
            None,
        )
        _single_test(
            mm.npc_position[idx],
            0,
            "NPC",
            mm.test_images[img],
            None,
            mm.map_area_box[idx],
        )
        _single_test(
            mm.npc_position[idx],
            0,
            "NPC",
            mm.test_images[img],
            mm.world_icons_box[idx],
            mm.map_area_box[idx],
        )

    # Lastly, an additional test is made to ensure that the function returns the same character position
    # No matter where the minimap is on-screen and no matter whether it is full or partial.
    # (Provided the character is actually in the same position, of course)
    images = [
        img
        for img in os.listdir(os.path.join(ROOT, "tests/images"))
        if img.startswith("test_character_position_minimap")
    ]
    positions = [
        mm.minimap.get_character_positions(0, client_img=cv2.imread(f"images/{img}"))
        for img in images
    ]
    assert all([pos == positions[0] for pos in positions])


def test_get_map_area_box(mm):
    for idx, img in enumerate(mm.test_images):
        assert (
            mm.minimap.get_map_area_box(mm.dummy_handle, mm.test_images[img], None)
            == mm.map_area_box[idx]
        )
        assert (
            mm.minimap.get_map_area_box(
                mm.dummy_handle, mm.test_images[img], mm.world_icons_box[idx]
            )
            == mm.map_area_box[idx]
        )


def test_get_minimap_title_box(mm):
    boxes = [
        (
            Box(
                left=entire_box.left,
                right=entire_box.right,
                top=entire_box.top,
                bottom=area_box.top,
            )
            if mm.minimap_state[idx] == "Full"
            else None
        )
        for idx, area_box, entire_box in zip(
            range(len(mm.map_area_box)),
            mm.map_area_box,
            mm.entire_minimap_box,
        )
    ]

    for idx, img in enumerate(mm.test_images):
        assert (
            mm.minimap.get_minimap_title_box(
                mm.dummy_handle, mm.test_images[img], None
            )
            == boxes[idx]
        )
        assert (
            mm.minimap.get_minimap_title_box(
                mm.dummy_handle, mm.test_images[img], mm.world_icons_box[idx]
            )
            == boxes[idx]
        )


def test__get_entire_minimap_box(mm):
    for idx, img in enumerate(mm.test_images):
        assert (
            mm.minimap.get_entire_minimap_box(
                mm.dummy_handle, mm.test_images[img], None
            )
            == mm.entire_minimap_box[idx]
        )
        assert (
            mm.minimap.get_entire_minimap_box(
                mm.dummy_handle, mm.test_images[img], mm.world_icons_box[idx]
            )
            == mm.entire_minimap_box[idx]
        )


def test_character_positions_are_builtin_ints(mm):
    """
    Coordinates come out of `np.where`, which yields `np.int64`. They must leave the
    detection boundary as builtin `int`, otherwise every downstream consumer -- the
    JSONL telemetry encoder above all, which renders `np.int64` as a quoted string --
    silently inherits a numpy scalar behind an `int` annotation.
    """
    for idx, img in enumerate(mm.test_images):
        positions = mm.minimap.get_character_positions(
            mm.dummy_handle, "Self", mm.test_images[img], None, None
        )
        if positions is None:
            continue
        for x, y in positions:
            assert type(x) is int
            assert type(y) is int


def test_minimap_boxes_have_builtin_int_coordinates(mm):
    """Same defect one layer up: box edges are derived from `np.where` indices."""
    for idx, img in enumerate(mm.test_images):
        boxes = (
            mm.minimap.get_entire_minimap_box(
                mm.dummy_handle, mm.test_images[img], None
            ),
            mm.minimap.get_map_area_box(mm.dummy_handle, mm.test_images[img], None),
        )
        for box in boxes:
            if box is None:
                continue
            for coordinate in (box.left, box.right, box.top, box.bottom):
                assert type(coordinate) is int
