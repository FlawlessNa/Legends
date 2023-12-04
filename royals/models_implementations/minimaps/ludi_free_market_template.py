import cv2
import numpy as np

from typing import Sequence

from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapPathingMechanics,
)


class LudiFreeMarketTemplate(MinimapPathingMechanics):
    map_area_width = 116
    map_area_height = 57
    bottom_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=111,
        top=38,
        bottom=38,
        name="bottom_platform",
        portal_source={
            "FreeMarketEntrance": [(100, 38)],
            "mid_left_portal": [(12, 38)],
        },
        portal_target={"FreeMarketEntrance": None, "mid_left_portal": [(13, 25)]},
    )
    mid_left_portal: MinimapFeature = MinimapFeature(
        left=11,
        right=14,
        top=25,
        bottom=25,
        name="mid_left_portal",
        portal_source={"top_platform_0": True},
        portal_target={"top_platform_0": [(10, 12)]},
        jump_down={"bottom_platform": True},
        jump={"mid_platform": True},
        fall={"bottom_platform": True},
    )
    mid_platform: MinimapFeature = MinimapFeature(
        left=17,
        right=87,
        top=25,
        bottom=25,
        name="mid_platform",
        jump_down={"bottom_platform": True},
        jump={
            "mid_left_portal": [(17, 25), (18, 25), (19, 25)],
            "mid_right_portal": [(85, 25), (86, 25), (87, 25)],
        },
        fall={"bottom_platform": True},
    )
    mid_right_portal: MinimapFeature = MinimapFeature(
        left=90,
        right=93,
        top=25,
        bottom=25,
        name="mid_right_portal",
        portal_source={"bottom_platform": True},
        portal_target={"bottom_platform": [(90, 38)]},
        jump={"mid_platform": True},
        fall={"bottom_platform": True},
    )
    top_platform_0: MinimapFeature = MinimapFeature(
        left=9,
        right=11,
        top=12,
        bottom=12,
        name="top_platform_0",
        jump={"top_platform_1": True},
        jump_down={"bottom_platform": True},
        fall={"bottom_platform": True},
    )
    top_platform_1: MinimapFeature = MinimapFeature(
        left=14,
        right=23,
        top=12,
        bottom=12,
        name="top_platform_1",
        jump_down={
            "mid_platform": [
                (17, 12),
                (18, 12),
                (19, 12),
                (20, 12),
                (21, 12),
                (22, 12),
                (23, 12),
            ],
            "mid_left_portal": [(14, 12)],
            "bottom_platform": [(16, 12), (15, 12)],
        },
        jump={
            "top_platform_0": [(14, 12), (15, 12)],
            "top_platform_2": [(23, 12), (22, 12)],
        },
        fall={"bottom_platform": [(14, 12)], "mid_platform": [(23, 12)]},
    )
    top_platform_2: MinimapFeature = MinimapFeature(
        left=25,
        right=34,
        top=12,
        bottom=12,
        name="top_platform_2",
        jump_down={"mid_platform": True},
        jump={
            "top_platform_1": [(25, 12), (26, 12)],
            "top_platform_3": [(33, 12), (34, 12)],
        },
        fall={"mid_platform": True},
    )
    top_platform_3: MinimapFeature = MinimapFeature(
        left=36,
        right=45,
        top=12,
        bottom=12,
        name="top_platform_3",
        jump_down={"mid_platform": True},
        jump={
            "top_platform_2": [(36, 12), (37, 12)],
            "top_platform_4": [(44, 12), (45, 12)],
        },
        fall={"mid_platform": True},
    )
    top_platform_4: MinimapFeature = MinimapFeature(
        left=48,
        right=56,
        top=12,
        bottom=12,
        name="top_platform_4",
        jump_down={"mid_platform": True},
        jump={
            "top_platform_3": [(48, 12), (49, 12)],
            "top_platform_5": [(55, 12), (56, 12)],
        },
        fall={"mid_platform": True},
    )
    top_platform_5: MinimapFeature = MinimapFeature(
        left=59,
        right=68,
        top=12,
        bottom=12,
        name="top_platform_5",
        jump_down={"mid_platform": True},
        jump={
            "top_platform_4": [(58, 12), (59, 12)],
            "top_platform_6": [(67, 12), (68, 12)],
        },
        fall={"mid_platform": True},
    )
    top_platform_6: MinimapFeature = MinimapFeature(
        left=70,
        right=79,
        top=12,
        bottom=12,
        name="top_platform_6",
        jump_down={"mid_platform": True},
        jump={
            "top_platform_5": [(70, 12), (71, 12)],
            "top_platform_7": [(78, 12), (79, 12)],
        },
        fall={"mid_platform": True},
    )
    top_platform_7: MinimapFeature = MinimapFeature(
        left=82,
        right=90,
        top=12,
        bottom=12,
        name="top_platform_7",
        jump_down={
            "mid_platform": [
                (82, 12),
                (83, 12),
                (84, 12),
                (85, 12),
                (86, 12),
                (87, 12),
            ],
            "bottom_platform": [(88, 12), (89, 12)],
        },
        jump={
            "top_platform_6": [(82, 12), (83, 12)],
            "top_right_portal": [(89, 12), (90, 12)],
        },
        fall={"mid_platform": [(82, 12)], "bottom_platform": [(90, 12)]},
    )
    top_right_portal: MinimapFeature = MinimapFeature(
        left=93,
        right=95,
        top=12,
        bottom=12,
        name="top_right_portal",
        portal_source={"mid_right_portal": True},
        portal_target={"mid_right_portal": [(91, 25)]},
        jump_down={"bottom_platform": True},
        fall={"bottom_platform": True},
        jump={"top_platform_7": [(93, 12), (94, 12)]},
    )
    # platform_5_ladder: MinimapFeature = MinimapFeature(
    #     left=73, right=74, top=12, bottom=23, name="platform_5_ladder"
    # )
    # platform_2_ladder: MinimapFeature = MinimapFeature(
    #     left=39, right=40, top=12, bottom=23, name="platform_2_ladder"
    # )
    # left_ladder: MinimapFeature = MinimapFeature(
    #     left=33, right=34, top=24, bottom=37, name="left_ladder"
    # )
    # right_ladder: MinimapFeature = MinimapFeature(
    #     left=82, right=83, top=24, bottom=36, name="right_ladder"
    # )

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
            pt1: Sequence = (feature.left, feature.top)
            pt2: Sequence = (feature.right, feature.bottom)
            cv2.line(canvas, pt1, pt2, (255, 255, 255), 1)
            # cv2.fillPoly(canvas, [np.array(rect)], (255, 255, 255))
        # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        # canvas = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, kernel)
        return canvas
