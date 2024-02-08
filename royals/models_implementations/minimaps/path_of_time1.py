from botting.utilities import Box
from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class PathOfTime1Minimap(MinimapPathingMechanics):
    map_area_width = 116
    map_area_height = 88

    # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    # minimap_speed: float = 7.686336000692184
    minimap_speed: float = 8.5
    jump_height: int = 5
    jump_distance: int = 7

    teleport_h_dist = 10
    teleport_v_up_dist = 8
    teleport_v_down_dist = 15

    door_spot = [(65, 54), (66, 54), (67, 54), (68, 54), (69, 54), (70, 54)]

    @property
    def central_node(self) -> tuple[int, int]:
        return int(self.third_platform_right_ladder.center[0]), int(
            self.third_platform_right_ladder.center[1]
        )

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return [
            self.first_platform,
            self.second_platform,
            self.third_platform,
            self.fourth_platform,
            self.fifth_platform,
            self.fourth_platform,
            self.third_platform,
            self.second_platform,
        ]

    first_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=27,
        top=9,
        bottom=9,
        name="first_platform",
    )
    second_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=44,
        top=24,
        bottom=24,
        name="second_platform",
    )
    third_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=61,
        top=39,
        bottom=39,
        name="third_platform",
    )
    fourth_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=79,
        top=54,
        bottom=54,
        name="fourth_platform",
    )
    fifth_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=112,
        top=69,
        bottom=69,
        name="fifth_platform",
    )
    cube1: MinimapFeature = MinimapFeature(
        left=16,
        right=18,
        top=7,
        bottom=7,
        name="cube1",
    )
    cube2: MinimapFeature = MinimapFeature(
        left=22,
        right=25,
        top=7,
        bottom=7,
        name="cube2",
    )
    side_platform1: MinimapFeature = MinimapFeature(
        left=31,
        right=34,
        top=9,
        bottom=9,
        name="side_platform1",
    )
    side_platform2: MinimapFeature = MinimapFeature(
        left=37,
        right=39,
        top=9,
        bottom=9,
        name="side_platform2",
    )
    cube3: MinimapFeature = MinimapFeature(
        left=13,
        right=19,
        top=22,
        bottom=22,
        name="cube3",
    )
    cube4: MinimapFeature = MinimapFeature(
        left=36,
        right=41,
        top=22,
        bottom=22,
        name="cube4",
    )
    cube5: MinimapFeature = MinimapFeature(
        left=36,
        right=39,
        top=19,
        bottom=19,
        name="cube5",
    )
    side_platform3: MinimapFeature = MinimapFeature(
        left=48,
        right=51,
        top=24,
        bottom=24,
        name="side_platform3",
    )
    side_platform4: MinimapFeature = MinimapFeature(
        left=54,
        right=56,
        top=24,
        bottom=24,
        name="side_platform4",
    )
    cube6: MinimapFeature = MinimapFeature(
        left=16,
        right=21,
        top=37,
        bottom=37,
        name="cube6",
    )
    cube7: MinimapFeature = MinimapFeature(
        left=29,
        right=32,
        top=37,
        bottom=37,
        name="cube7",
    )
    cube8: MinimapFeature = MinimapFeature(
        left=54,
        right=57,
        top=37,
        bottom=37,
        name="cube8",
    )
    side_platform5: MinimapFeature = MinimapFeature(
        left=65,
        right=67,
        top=39,
        bottom=39,
        name="side_platform5",
    )
    side_platform_6: MinimapFeature = MinimapFeature(
        left=71,
        right=73,
        top=39,
        bottom=39,
        name="side_platform_6",
    )
    cube9: MinimapFeature = MinimapFeature(
        left=12,
        right=15,
        top=52,
        bottom=52,
        name="cube9",
    )
    cube10: MinimapFeature = MinimapFeature(
        left=36,
        right=41,
        top=52,
        bottom=52,
        name="cube10",
    )
    cube11: MinimapFeature = MinimapFeature(
        left=71,
        right=74,
        top=52,
        bottom=52,
        name="cube11",
    )
    side_platform7: MinimapFeature = MinimapFeature(
        left=82,
        right=84,
        top=54,
        bottom=54,
        name="side_platform7",
    )
    side_platform8: MinimapFeature = MinimapFeature(
        left=88,
        right=90,
        top=54,
        bottom=54,
        name="side_platform8",
    )
    cube12: MinimapFeature = MinimapFeature(
        left=8,
        right=18,
        top=67,
        bottom=67,
        name="cube12",
    )
    cube13: MinimapFeature = MinimapFeature(
        left=9,
        right=15,
        top=64,
        bottom=64,
        name="cube13",
    )
    cube14: MinimapFeature = MinimapFeature(
        left=22,
        right=24,
        top=67,
        bottom=67,
        name="cube14",
    )
    cube15: MinimapFeature = MinimapFeature(
        left=38,
        right=41,
        top=67,
        bottom=67,
        name="cube15",
    )
    cube16: MinimapFeature = MinimapFeature(
        left=49,
        right=57,
        top=67,
        bottom=67,
        name="cube16",
    )
    cube17: MinimapFeature = MinimapFeature(
        left=53,
        right=56,
        top=64,
        bottom=64,
        name="cube17",
    )
    cube18: MinimapFeature = MinimapFeature(
        left=84,
        right=90,
        top=67,
        bottom=67,
        name="cube18",
    )
    cube19: MinimapFeature = MinimapFeature(
        left=102,
        right=104,
        top=67,
        bottom=67,
        name="cube19",
    )
    first_platform_ladder: MinimapFeature = MinimapFeature(
        left=10,
        right=10,
        top=10,
        bottom=20,
        name="first_platform_ladder",
    )
    second_platform_ladder: MinimapFeature = MinimapFeature(
        left=26,
        right=26,
        top=25,
        bottom=35,
        name="second_platform_ladder",
    )
    third_platform_left_ladder: MinimapFeature = MinimapFeature(
        left=10,
        right=10,
        top=40,
        bottom=50,
        name="third_platform_left_ladder",
    )
    third_platform_right_ladder: MinimapFeature = MinimapFeature(
        left=44,
        right=44,
        top=40,
        bottom=50,
        name="third_platform_right_ladder",
    )
    fourth_platform_left_ladder: MinimapFeature = MinimapFeature(
        left=26,
        right=26,
        top=55,
        bottom=65,
        name="fourth_platform_left_ladder",
    )
    fourth_platform_right_ladder: MinimapFeature = MinimapFeature(
        left=60,
        right=60,
        top=55,
        bottom=65,
        name="fourth_platform_right_ladder",
    )
