from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class KerningLine1Area1Minimap(MinimapPathingMechanics):
    map_area_width = 259
    map_area_height = 79

    minimap_speed: float = 6.86478169800788  # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    jump_height: int = 5
    jump_distance: int = 4

    teleport_v_up_dist = 8
    teleport_h_dist = 9
    teleport_v_down_dist = 11

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return []

    bottom_platform: MinimapFeature = MinimapFeature(
        left=20,
        right=238,
        top=57,
        bottom=57,
        name="bottom_platform",
    )
    fourth_wagon: MinimapFeature = MinimapFeature(
        left=216,
        right=228,
        top=53,
        bottom=53,
        name="fourth_wagon",
    )
    third_wagon: MinimapFeature = MinimapFeature(
        left=172,
        right=185,
        top=53,
        bottom=53,
        name="third_wagon",
    )
    second_wagon: MinimapFeature = MinimapFeature(
        left=100,
        right=113,
        top=53,
        bottom=53,
        name="second_wagon",
    )
    first_wagon: MinimapFeature = MinimapFeature(
        left=50,
        right=63,
        top=53,
        bottom=53,
        name="first_wagon",
    )
    first_ladder_bot_to_main: MinimapFeature = MinimapFeature(
        left=32,
        right=32,
        top=50,
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
    main_platform: MinimapFeature = MinimapFeature(
        left=20,
        right=238,
        top=49,
        bottom=49,
        name="main_platform",
    )
    platform_1: MinimapFeature = MinimapFeature(
        left=46,
        right=93,
        top=26,
        bottom=26,
        name="platform_1",
    )
    platform_1_right_ladder: MinimapFeature = MinimapFeature(
        left=87, right=87, top=27, bottom=37, name="platform_1_right_ladder"
    )
    platform_1_left_ladder: MinimapFeature = MinimapFeature(
        left=56, right=56, top=27, bottom=32, name="platform_1_left_ladder"
    )
    platform_2: MinimapFeature = MinimapFeature(
        left=102, right=132, top=30, bottom=30, name="platform_2"
    )
    platform_2_ladder: MinimapFeature = MinimapFeature(
        left=118, right=118, top=31, bottom=40, name="platform_2_ladder"
    )
    platform_3: MinimapFeature = MinimapFeature(
        left=136, right=154, top=34, bottom=34, name="platform_3"
    )
    platform_4: MinimapFeature = MinimapFeature(
        left=153, right=178, top=26, bottom=26, name="platform_4"
    )
    platform_4_right_ladder: MinimapFeature = MinimapFeature(
        left=175, right=175, top=27, bottom=36, name="platform_4_right_ladder"
    )
    platform_4_left_ladder: MinimapFeature = MinimapFeature(
        left=158, right=158, top=27, bottom=40, name="platform_4_left_ladder"
    )
    platform_5: MinimapFeature = MinimapFeature(
        left=181, right=206, top=26, bottom=26, name="platform_5"
    )
    platform_5_ladder: MinimapFeature = MinimapFeature(
        left=199, right=199, top=27, bottom=41, name="platform_5_ladder"
    )
    safe_spot_right: MinimapFeature = MinimapFeature(
        left=215, right=222, top=30, bottom=30, name="safe_spot_right"
    )
    safe_spot_right_ladder: MinimapFeature = MinimapFeature(
        left=218, right=218, top=31, bottom=40, name="safe_spot_right_ladder"
    )
    platform_6: MinimapFeature = MinimapFeature(
        left=29, right=54, top=34, bottom=34, name="platform_6"
    )
    platform_6_ladder: MinimapFeature = MinimapFeature(
        left=48, right=48, top=35, bottom=40, name="platform_6_ladder"
    )
    platform_7: MinimapFeature = MinimapFeature(
        left=35, right=65, top=41, bottom=41, name="platform_7"
    )
    platform_7_ladder: MinimapFeature = MinimapFeature(
        left=56, right=56, top=42, bottom=48, name="platform_7_ladder"
    )
    platform_8_ladder: MinimapFeature = MinimapFeature(
        left=88, right=88, top=39, bottom=46, name="platform_8_ladder"
    )
    platform_8: MinimapFeature = MinimapFeature(
        left=74, right=110, top=38, bottom=38, name="platform_8"
    )
    platform_9: MinimapFeature = MinimapFeature(
        left=119, right=172, top=41, bottom=41, name="platform_9"
    )
    platform_9_right_ladder: MinimapFeature = MinimapFeature(
        left=169, right=169, top=42, bottom=48, name="platform_9_right_ladder"
    )
    platform_9_left_ladder: MinimapFeature = MinimapFeature(
        left=141, right=141, top=42, bottom=48, name="platform_9_left_ladder"
    )
    safe_spot_left: MinimapFeature = MinimapFeature(
        left=176, right=178, top=38, bottom=38, name="safe_spot_left"
    )
    platform_10: MinimapFeature = MinimapFeature(
        left=181, right=228, top=41, bottom=41, name="platform_10"
    )
    platform_10_ladder: MinimapFeature = MinimapFeature(
        left=209, right=209, top=42, bottom=48, name="platform_10_ladder"
    )
