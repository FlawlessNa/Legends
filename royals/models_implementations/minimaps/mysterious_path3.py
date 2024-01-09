from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapPathingMechanics,
)


class MysteriousPath3Minimap(MinimapPathingMechanics):
    map_area_width = 254
    map_area_height = 87

    # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    minimap_speed: float = 6.9642265749772365
    jump_height: int = 5
    jump_distance: int = 5
    jump_down_limit: int = 30

    teleport_h_dist = 9
    teleport_v_up_dist = 5
    teleport_v_down_dist = 9

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return [
            self.bot_platform,
            self.mid_platform,
            self.top_platform,
        ]

    car_safe_spot: MinimapFeature = MinimapFeature(
        left=138,
        right=152,
        top=62,
        bottom=62,
        name="car_safe_spot",
    )
    car_odd_spot1: MinimapFeature = MinimapFeature(
        left=136,
        right=137,
        top=64,
        bottom=64,
        name="car_odd_spot1",
    )
    car_odd_spot2: MinimapFeature = MinimapFeature(
        left=135,
        right=137,
        top=65,
        bottom=65,
        name="car_odd_spot2",
    )
    bot_platform: MinimapFeature = MinimapFeature(
        left=91,
        right=185,
        top=68,
        bottom=68,
        name="bot_platform",
        central_node=(115, 68),
    )
    first_ladder: MinimapFeature = MinimapFeature(
        left=101,
        right=101,
        top=44,
        bottom=66,
        name="first_ladder",
    )
    mid_platform: MinimapFeature = MinimapFeature(
        left=83,
        right=134,
        top=43,
        bottom=43,
        name="mid_platform",
    )
    second_ladder: MinimapFeature = MinimapFeature(
        left=123,
        right=123,
        top=22,
        bottom=39,
        name="second_ladder",
    )
    plank_37: MinimapFeature = MinimapFeature(
        left=113,
        right=116,
        top=37,
        bottom=37,
        name="plank_37"
    )
    plank_38: MinimapFeature = MinimapFeature(
        left=113,
        right=116,
        top=38,
        bottom=38,
        name="plank_38"
    )
    plank_39: MinimapFeature = MinimapFeature(
        left=113,
        right=116,
        top=39,
        bottom=39,
        name="plank_39"
    )
    plank_40: MinimapFeature = MinimapFeature(
        left=113,
        right=116,
        top=40,
        bottom=40,
        name="plank_40"
    )
    plank_41: MinimapFeature = MinimapFeature(
        left=113,
        right=116,
        top=41,
        bottom=41,
        name="plank_41"
    )
    box1: MinimapFeature = MinimapFeature(
        left=115,
        right=118,
        top=40,
        bottom=40,
        name="box1",
    )
    box2: MinimapFeature = MinimapFeature(
        left=120,
        right=123,
        top=40,
        bottom=40,
        name="box2",
    )

    top_platform: MinimapFeature = MinimapFeature(
        left=105,
        right=167,
        top=21,
        bottom=21,
        name="top_platform",
    )
    box3: MinimapFeature = MinimapFeature(
        left=146,
        right=154,
        top=18,
        bottom=18,
        name="box3",
    )
    box4: MinimapFeature = MinimapFeature(
        left=151,
        right=154,
        top=15,
        bottom=15,
        name="box4",
    )
    right_platform: MinimapFeature = MinimapFeature(
        left=150,
        right=184,
        top=39,
        bottom=39,
        name="right_platform",
    )
    box5: MinimapFeature = MinimapFeature(
        left=158,
        right=162,
        top=64,
        bottom=64,
        name="box5",
    )
    left_boat_upper_59: MinimapFeature = MinimapFeature(
        left=52,
        right=94,
        top=59,
        bottom=59,
        name="left_boat_upper_59",
    )
    left_boat_upper_60: MinimapFeature = MinimapFeature(
        left=52,
        right=94,
        top=60,
        bottom=60,
        name="left_boat_upper_60",
    )
    left_boat_upper_61: MinimapFeature = MinimapFeature(
        left=52,
        right=94,
        top=61,
        bottom=61,
        name="left_boat_upper_61",
    )
    left_boat_upper_62: MinimapFeature = MinimapFeature(
        left=52,
        right=94,
        top=62,
        bottom=62,
        name="left_boat_upper_62",
    )
    left_boat_middle_67: MinimapFeature = MinimapFeature(
        left=54,
        right=92,
        top=67,
        bottom=67,
        name="left_boat_middle_67",
    )
    left_boat_middle_66: MinimapFeature = MinimapFeature(
        left=54,
        right=92,
        top=66,
        bottom=66,
        name="left_boat_middle_66",
    )
    left_boat_bottom_73: MinimapFeature = MinimapFeature(
        left=54,
        right=92,
        top=73,
        bottom=73,
        name="left_boat_bottom_73",
    )
    left_boat_bottom_72: MinimapFeature = MinimapFeature(
        left=54,
        right=92,
        top=72,
        bottom=72,
        name="left_boat_bottom_72",
    )
    right_boat_bottom_73: MinimapFeature = MinimapFeature(
        left=172,
        right=200,
        top=73,
        bottom=73,
        name="right_boat_bottom_73",
    )

    right_platform_bench: MinimapFeature = MinimapFeature(
        left=173,
        right=179,
        top=37,
        bottom=37,
        name="right_platform_bench",
    )
    right_platform_sign_1: MinimapFeature = MinimapFeature(
        left=174,
        right=177,
        top=31,
        bottom=31,
        name="right_platform_sign_1",
    )
    right_platform_thrash: MinimapFeature = MinimapFeature(
        left=179,
        right=183,
        top=34,
        bottom=34,
        name="right_platform_thrash",
    )
    right_platform_sign_2: MinimapFeature = MinimapFeature(
        left=181,
        right=185,
        top=29,
        bottom=29,
        name="right_platform_sign_2",
    )
