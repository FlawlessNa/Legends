import cv2
import numpy as np

from functools import cached_property

from botting.utilities import Box
from royals.interface import Minimap
from royals.models_implementations.mechanics import MinimapPathingMechanics


class LudiFreeMarketTemplate(Minimap, MinimapPathingMechanics):
    map_area_width = 116
    map_area_height = 57
    height_limit_for_jump_down = None
    horizontal_jump_distance = 3
    bottom_platform: Box = Box(left=12, right=120, top=37, bottom=38, name="bottom_platform")
    bottom_left_portal: Box = Box(left=20, right=22, top=37, bottom=38, name="bottom_left_portal")
    mid_left_portal: Box = Box(left=20, right=23, top=24, bottom=25, name="mid_left_portal")
    mid_platform: Box = Box(left=25, right=96, top=24, bottom=25, name="mid_platform")
    mid_right_portal: Box = Box(left=99, right=101, top=24, bottom=25, name="mid_right_portal")
    top_platform_0: Box = Box(left=17, right=20, top=11, bottom=12, name="top_platform_0")
    top_platform_1: Box = Box(left=23, right=31, top=11, bottom=12, name="top_platform_1")
    top_platform_2: Box = Box(left=33, right=42, top=11, bottom=12, name="top_platform_2")
    top_platform_3: Box = Box(left=45, right=53, top=11, bottom=12, name="top_platform_3")
    top_platform_4: Box = Box(left=56, right=65, top=11, bottom=12, name="top_platform_4")
    top_platform_5: Box = Box(left=67, right=76, top=11, bottom=12, name="top_platform_5")
    top_platform_6: Box = Box(left=79, right=87, top=11, bottom=12, name="top_platform_6")
    top_platform_7: Box = Box(left=90, right=99, top=11, bottom=12, name="top_platform_7")
    top_right_portal: Box = Box(left=101, right=104, top=11, bottom=12, name="top_right_portal")
    platform_5_ladder: Box = Box(left=73, right=74, top=11, bottom=23, name="platform_5_ladder")
    platform_2_ladder: Box = Box(left=39, right=40, top=11, bottom=23, name="platform_2_ladder")
    left_ladder: Box = Box(left=33, right=34, top=24, bottom=37, name="left_ladder")
    right_ladder: Box = Box(left=82, right=83, top=24, bottom=36, name="right_ladder")

    @property
    def features(self) -> dict[str, Box]:
        return super().features

    @property
    def teleporters(self) -> list[tuple[Box, Box]]:
        return [
            (self.bottom_left_portal, self.mid_left_portal),
            (self.mid_left_portal, self.top_platform_0),
            (self.top_right_portal, self.mid_right_portal),
        ]

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        Creates a Grid-like image used for pathfinding algorithm.
        :param image: Original minimap area image.
        :return: Binary image with white pixels representing walkable areas.
        """
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        canvas = np.zeros_like(image)
        for feature in self.features.values():
            if feature.width == 1:
                pt1 = (feature.left, feature.top)
                pt2 = (feature.left, feature.bottom)
                # rect = np.array(
                #     [
                #         [feature.left, feature.top],
                #         [feature.left, feature.bottom],
                #         [feature.right, feature.bottom],
                #         [feature.right, feature.top],
                #     ]
                # )
            elif feature.height == 1:
                pt1 = (feature.left, feature.top)
                pt2 = (feature.right, feature.top)
            else:
                raise ValueError(f"Feature {feature} is not a line.")
            cv2.line(canvas, pt1, pt2, 255, 1)
            # cv2.fillPoly(canvas, [np.array(rect)], (255, 255, 255))
        # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        # canvas = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, kernel)
        return canvas
