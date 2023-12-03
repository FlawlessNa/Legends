import cv2
import os
import numpy as np
import re

from unittest import TestCase

from botting.utilities import (
    Box,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
)
from paths import ROOT
from royals.interface import Minimap


class MinimapTester(Minimap):
    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass


class TestMinimap(TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dummy_handle = 0
        cls.minimap = MinimapTester()  # This allows us to create a Minimap instance
        images = [
            img
            for img in os.listdir(os.path.join(ROOT, "tests/images"))
            if img.startswith("test_minimap")
        ]
        images.sort(key=lambda x: eval(re.search(r"\d+", x).group()))
        cls.test_images = {img: cv2.imread(f"images/{img}") for img in images}
        cls._is_displayed = [
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
        ]
        cls._minimap_state = [
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
        ]
        cls._world_icons_box = [
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
        ]
        # Only applicable when minimap is fully displayed.
        _extra_widths = [18, 18, None, None, 0, 0, 0, 0, 10, None, 0, 10]
        _map_area_box = [
            Box(
                left=_map_area_top_left[i][0]
                + CLIENT_HORIZONTAL_MARGIN_PX
                + _extra_widths[i] // 2,
                right=_map_area_bot_right[i][0]
                + CLIENT_HORIZONTAL_MARGIN_PX
                + 1
                - _extra_widths[i] // 2,
                top=_map_area_top_left[i][1] + CLIENT_VERTICAL_MARGIN_PX,
                bottom=_map_area_bot_right[i][1] + CLIENT_VERTICAL_MARGIN_PX + 1,
            )
            if _map_area_top_left[i] is not None
            else None
            for i in range(len(_world_icons_top_left))
        ]
        cls._map_area_box = _map_area_box
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
        ]
        cls._entire_minimap_box = [
            Box(
                left=_entire_minimap_top_left[i][0] + CLIENT_HORIZONTAL_MARGIN_PX,
                right=_map_area_bot_right[i][0] + CLIENT_HORIZONTAL_MARGIN_PX + 1,
                top=_entire_minimap_top_left[i][1] + CLIENT_VERTICAL_MARGIN_PX,
                bottom=_map_area_bot_right[i][1] + CLIENT_VERTICAL_MARGIN_PX + 1,
            )
            if _map_area_top_left[i] is not None
            else None
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
                            pos[0]
                            - _map_area_box[i].left
                            + CLIENT_HORIZONTAL_MARGIN_PX,
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
                            pos[0]
                            - _map_area_box[i].left
                            + CLIENT_HORIZONTAL_MARGIN_PX,
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
                            pos[0]
                            - _map_area_box[i].left
                            + CLIENT_HORIZONTAL_MARGIN_PX,
                            pos[1]
                            - _map_area_box[i].top
                            + CLIENT_VERTICAL_MARGIN_PX
                            - 1,
                        )
                        for pos in position
                    ]
                )

        cls._self_position = _corrected_self_position
        cls._stranger_position = _corrected_stranger_position
        cls._npc_position = _corrected_npc_position
        _buddy_position = NotImplemented
        _guildie_position = NotImplemented
        _party_position = NotImplemented

    def test_is_displayed(self):
        """
        We test the function with both the image provided and/or the world icon detection box provided.
        :return:
        """
        for idx, img in enumerate(self.test_images):
            self.assertEqual(
                self.minimap.is_displayed(
                    self.dummy_handle, self.test_images[img], None
                ),
                self._is_displayed[idx],
            )
            self.assertEqual(
                self.minimap.is_displayed(
                    self.dummy_handle, self.test_images[img], self._world_icons_box[idx]
                ),
                self._is_displayed[idx],
            )

    def test_get_minimap_state(self):
        for idx, img in enumerate(self.test_images):
            self.assertEqual(
                self.minimap.get_minimap_state(
                    self.dummy_handle, self.test_images[img], None
                ),
                self._minimap_state[idx],
            )
            self.assertEqual(
                self.minimap.get_minimap_state(
                    self.dummy_handle, self.test_images[img], self._world_icons_box[idx]
                ),
                self._minimap_state[idx],
            )

    def test_get_character_positions(self):
        """
        TODO - Test with "Party" members as well as "Guild" members and "Buddies".
        """

        def _single_test(expected, *params):
            actual = self.minimap.get_character_positions(*params)
            if expected is None:
                return self.assertIsNone(actual)
            return self.assertEqual(
                set(actual),
                set(expected),
            )

        for idx, img in enumerate(self.test_images):
            _single_test(
                self._self_position[idx], 0, "Self", self.test_images[img], None, None
            )
            _single_test(
                self._self_position[idx],
                0,
                "Self",
                self.test_images[img],
                self._world_icons_box[idx],
                None,
            )
            _single_test(
                self._self_position[idx],
                0,
                "Self",
                self.test_images[img],
                None,
                self._map_area_box[idx],
            )
            _single_test(
                self._self_position[idx],
                0,
                "Self",
                self.test_images[img],
                self._world_icons_box[idx],
                self._map_area_box[idx],
            )

            _single_test(
                self._stranger_position[idx],
                0,
                "Stranger",
                self.test_images[img],
                None,
                None,
            )
            _single_test(
                self._stranger_position[idx],
                0,
                "Stranger",
                self.test_images[img],
                self._world_icons_box[idx],
                None,
            )
            _single_test(
                self._stranger_position[idx],
                0,
                "Stranger",
                self.test_images[img],
                None,
                self._map_area_box[idx],
            )
            _single_test(
                self._stranger_position[idx],
                0,
                "Stranger",
                self.test_images[img],
                self._world_icons_box[idx],
                self._map_area_box[idx],
            )

            _single_test(
                self._npc_position[idx], 0, "NPC", self.test_images[img], None, None
            )
            _single_test(
                self._npc_position[idx],
                0,
                "NPC",
                self.test_images[img],
                self._world_icons_box[idx],
                None,
            )
            _single_test(
                self._npc_position[idx],
                0,
                "NPC",
                self.test_images[img],
                None,
                self._map_area_box[idx],
            )
            _single_test(
                self._npc_position[idx],
                0,
                "NPC",
                self.test_images[img],
                self._world_icons_box[idx],
                self._map_area_box[idx],
            )

        # Lastly, an additional test is made to ensure that the function returns the same character position
        # No matter where the minimap is on-screen and no matter whether it is full or partial.
        # (Provided the character is actually in the same position, of course)
        images = [
            img
            for img in os.listdir(os.path.join(ROOT, "tests/images"))
            if img.startswith("test_character_position_minimap")
        ]
        positions = [self.minimap.get_character_positions(0, client_img=cv2.imread(f"images/{img}")) for img in images]
        self.assertTrue(all([pos == positions[0] for pos in positions]))

    def test_get_map_area_box(self):
        for idx, img in enumerate(self.test_images):
            self.assertEqual(
                self.minimap.get_map_area_box(
                    self.dummy_handle, self.test_images[img], None
                ),
                self._map_area_box[idx],
            )
            self.assertEqual(
                self.minimap.get_map_area_box(
                    self.dummy_handle, self.test_images[img], self._world_icons_box[idx]
                ),
                self._map_area_box[idx],
            )

    def test_get_minimap_title_box(self):
        boxes = [
            Box(
                left=entire_box.left,
                right=entire_box.right,
                top=entire_box.top,
                bottom=area_box.top,
            )
            if self._minimap_state[idx] == "Full"
            else None
            for idx, area_box, entire_box in zip(
                range(len(self._map_area_box)),
                self._map_area_box,
                self._entire_minimap_box,
            )
        ]

        for idx, img in enumerate(self.test_images):
            self.assertEqual(
                self.minimap.get_minimap_title_box(
                    self.dummy_handle, self.test_images[img], None
                ),
                boxes[idx],
            )
            self.assertEqual(
                self.minimap.get_minimap_title_box(
                    self.dummy_handle, self.test_images[img], self._world_icons_box[idx]
                ),
                boxes[idx],
            )

    def test__get_entire_minimap_box(self):
        for idx, img in enumerate(self.test_images):
            self.assertEqual(
                self.minimap._get_entire_minimap_box(
                    self.dummy_handle, self.test_images[img], None
                ),
                self._entire_minimap_box[idx],
            )
            self.assertEqual(
                self.minimap._get_entire_minimap_box(
                    self.dummy_handle, self.test_images[img], self._world_icons_box[idx]
                ),
                self._entire_minimap_box[idx],
            )
