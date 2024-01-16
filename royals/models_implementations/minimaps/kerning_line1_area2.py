from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class KerningLine1Area2Minimap(MinimapPathingMechanics):
    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return [
            self.platform_1,
            self.platform_2,
            self.platform_3,
            self.platform_4,
            self.platform_5,
            self.platform_6,
            self.platform_7,
            self.platform_8,
            self.platform_9,
            self.platform_10,
        ]

    @property
    def central_node(self) -> tuple[int, int]:
        return int(self.safe_spot.center[0]), int(self.safe_spot.center[1])

    map_area_width = 259
    map_area_height = 79

    # minimap_speed: float = 7.466178677298277  # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    minimap_speed = 7.0
    jump_height: int = 5
    jump_distance: int = 5

    teleport_h_dist = 9
    teleport_v_down_dist = 10
    teleport_v_up_dist = 8

    bottom_platform: MinimapFeature = MinimapFeature(
        left=20,
        right=238,
        top=57,
        bottom=57,
        name="bottom_platform",
    )
    main_platform: MinimapFeature = MinimapFeature(
        left=20,
        right=238,
        top=49,
        bottom=49,
        name="main_platform",
    )
    first_wagon: MinimapFeature = MinimapFeature(
        left=50,
        right=62,
        top=53,
        bottom=53,
        name="first_wagon",
    )
    second_wagon: MinimapFeature = MinimapFeature(
        left=101,
        right=113,
        top=53,
        bottom=53,
        name="second_wagon",
    )
    third_wagon: MinimapFeature = MinimapFeature(
        left=173,
        right=185,
        top=53,
        bottom=53,
        name="third_wagon",
    )
    fourth_wagon: MinimapFeature = MinimapFeature(
        left=216,
        right=228,
        top=53,
        bottom=53,
        name="fourth_wagon",
    )
    first_ladder_bot_to_main: MinimapFeature = MinimapFeature(
        left=32,
        right=32,
        top=49,
        bottom=56,
        name="first_ladder_bot_to_main",
    )

    second_ladder_bot_to_main: MinimapFeature = MinimapFeature(
        left=98,
        right=98,
        top=50,
        bottom=56,
        name="second_ladder_bot_to_main",
    )
    third_ladder_bot_to_main: MinimapFeature = MinimapFeature(
        left=127,
        right=127,
        top=50,
        bottom=56,
        name="third_ladder_bot_to_main",
    )
    fourth_ladder_bot_to_main: MinimapFeature = MinimapFeature(
        left=162,
        right=162,
        top=50,
        bottom=56,
        name="fourth_ladder_bot_to_main",
    )
    fifth_ladder_bot_to_main: MinimapFeature = MinimapFeature(
        left=199,
        right=199,
        top=50,
        bottom=56,
        name="fifth_ladder_bot_to_main",
    )
    platform_1: MinimapFeature = MinimapFeature(
        left=35,
        right=65,
        top=41,
        bottom=41,
        name="platform_1",
    )
    platform_2: MinimapFeature = MinimapFeature(
        left=41,
        right=71,
        top=34,
        bottom=34,
        name="platform_2",
    )
    platform_3: MinimapFeature = MinimapFeature(
        left=46,
        right=87,
        top=26,
        bottom=26,
        name="platform_3",
    )
    platform_3_ladder: MinimapFeature = MinimapFeature(
        left=56,
        right=56,
        top=27,
        bottom=33,
        name="platform_3_ladder",
    )
    platform_1_ladder: MinimapFeature = MinimapFeature(
        left=56,
        right=56,
        top=42,
        bottom=48,
        name="platform_1_ladder",
    )
    platform_4: MinimapFeature = MinimapFeature(
        left=69,
        right=104,
        top=38,
        bottom=38,
        name="platform_4",
    )
    platform_4_ladder: MinimapFeature = MinimapFeature(
        left=85,
        right=85,
        top=39,
        bottom=48,
        name="platform_4_ladder",
    )
    safe_spot: MinimapFeature = MinimapFeature(
        left=107,
        right=110,
        top=43,
        bottom=43,
        name="safe_spot",
    )
    platform_5: MinimapFeature = MinimapFeature(
        left=114,
        right=160,
        top=41,
        bottom=41,
        name="platform_5",
    )
    platform_5_ladder: MinimapFeature = MinimapFeature(
        left=141,
        right=141,
        top=42,
        bottom=48,
        name="platform_5_ladder",
    )
    platform_6: MinimapFeature = MinimapFeature(
        left=102,
        right=149,
        top=30,
        bottom=30,
        name="platform_6",
    )
    platform_6_ladder: MinimapFeature = MinimapFeature(
        left=118,
        right=118,
        top=31,
        bottom=41,
        name="platform_6_ladder",
    )
    platform_7: MinimapFeature = MinimapFeature(
        left=153,
        right=200,
        top=26,
        bottom=26,
        name="platform_7",
    )
    platform_7_ladder: MinimapFeature = MinimapFeature(
        left=175,
        right=175,
        top=27,
        bottom=37,
        name="platform_7_ladder",
    )
    platform_8: MinimapFeature = MinimapFeature(
        left=164,
        right=189,
        top=38,
        bottom=38,
        name="platform_8",
    )
    platform_8_ladder: MinimapFeature = MinimapFeature(
        left=169,
        right=169,
        top=39,
        bottom=48,
        name="platform_8_ladder",
    )
    platform_9: MinimapFeature = MinimapFeature(
        left=193,
        right=228,
        top=41,
        bottom=41,
        name="platform_9",
    )
    platform_9_ladder: MinimapFeature = MinimapFeature(
        left=209,
        right=209,
        top=42,
        bottom=48,
        name="platform_9_ladder",
    )
    platform_10: MinimapFeature = MinimapFeature(
        left=198,
        right=222,
        top=30,
        bottom=30,
        name="platform_10",
    )
    platform_10_ladder: MinimapFeature = MinimapFeature(
        left=219,
        right=219,
        top=31,
        bottom=41,
        name="platform_10_ladder",
    )
