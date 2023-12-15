from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class LudiFreeMarketTemplate(MinimapPathingMechanics):
    map_area_width = 116
    map_area_height = 57
    minimap_speed: float = 7.891176807337812  # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    bottom_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=111,
        top=38,
        bottom=38,
        name="bottom_platform",
        connections=[
            MinimapConnection(None, MinimapConnection.PORTAL, [(100, 38)]),
            MinimapConnection(
                "mid_left_portal", MinimapConnection.PORTAL, [(12, 38)], [(13, 25)]
            ),
            MinimapConnection("left_ladder", MinimapConnection.JUMP_ANY_AND_UP),
            MinimapConnection("right_ladder", MinimapConnection.JUMP_ANY_AND_UP),
        ],
    )
    mid_left_portal: MinimapFeature = MinimapFeature(
        left=11,
        right=14,
        top=25,
        bottom=25,
        name="mid_left_portal",
        connections=[
            MinimapConnection(
                "top_platform_0",
                MinimapConnection.PORTAL,
                [(12, 25), (13, 25)],
                [(10, 12)],
            ),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_ANY),
        ]
    )
    mid_platform: MinimapFeature = MinimapFeature(
        left=17,
        right=86,
        top=25,
        bottom=25,
        name="mid_platform",
        connections=[
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_ANY),
            MinimapConnection("mid_left_portal", MinimapConnection.JUMP_LEFT),
            MinimapConnection("mid_right_portal", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("platform_2_ladder", MinimapConnection.JUMP_ANY_AND_UP),
            MinimapConnection("platform_5_ladder", MinimapConnection.JUMP_ANY_AND_UP),
        ],
    )
    mid_right_portal: MinimapFeature = MinimapFeature(
        left=90,
        right=93,
        top=25,
        bottom=25,
        name="mid_right_portal",
        connections=[
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_ANY),
            MinimapConnection(
                "bottom_platform", MinimapConnection.PORTAL, [(91, 25), (92, 25)], [(90, 38)]
            ),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_LEFT),
        ],
    )
    top_platform_0: MinimapFeature = MinimapFeature(
        left=9,
        right=11,
        top=12,
        bottom=12,
        name="top_platform_0",
        connections=[
            MinimapConnection("top_platform_1", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_ANY),
        ],
    )
    top_platform_1: MinimapFeature = MinimapFeature(
        left=14,
        right=22,
        top=12,
        bottom=12,
        name="top_platform_1",
        connections=[
            MinimapConnection("top_platform_0", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_platform_2", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_LEFT),
            MinimapConnection("mid_platform", MinimapConnection.FALL_RIGHT),
        ],
    )
    top_platform_2: MinimapFeature = MinimapFeature(
        left=25,
        right=33,
        top=12,
        bottom=12,
        name="top_platform_2",
        connections=[
            MinimapConnection("top_platform_1", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_platform_3", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.FALL_ANY),
        ],
    )
    top_platform_3: MinimapFeature = MinimapFeature(
        left=36,
        right=45,
        top=12,
        bottom=12,
        name="top_platform_3",
        connections=[
            MinimapConnection("top_platform_2", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_platform_4", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.FALL_ANY),
        ],
    )
    top_platform_4: MinimapFeature = MinimapFeature(
        left=48,
        right=56,
        top=12,
        bottom=12,
        name="top_platform_4",
        connections=[
            MinimapConnection("top_platform_3", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_platform_5", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.FALL_ANY),
        ],
    )
    top_platform_5: MinimapFeature = MinimapFeature(
        left=59,
        right=67,
        top=12,
        bottom=12,
        name="top_platform_5",
        connections=[
            MinimapConnection("top_platform_4", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_platform_6", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.FALL_ANY),
        ],
    )
    top_platform_6: MinimapFeature = MinimapFeature(
        left=70,
        right=78,
        top=12,
        bottom=12,
        name="top_platform_6",
        connections=[
            MinimapConnection("top_platform_5", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_platform_7", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.FALL_ANY),
        ],
    )
    top_platform_7: MinimapFeature = MinimapFeature(
        left=82,
        right=90,
        top=12,
        bottom=12,
        name="top_platform_7",
        connections=[
            MinimapConnection("top_platform_6", MinimapConnection.JUMP_LEFT),
            MinimapConnection("top_right_portal", MinimapConnection.JUMP_RIGHT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("mid_platform", MinimapConnection.FALL_LEFT),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_RIGHT),
        ],
    )
    top_right_portal: MinimapFeature = MinimapFeature(
        left=93,
        right=95,
        top=12,
        bottom=12,
        name="top_right_portal",
        connections=[
            MinimapConnection("top_platform_7", MinimapConnection.JUMP_LEFT),
            MinimapConnection("mid_right_portal", MinimapConnection.PORTAL, [(94, 25)], [(91, 25)]),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_DOWN),
            MinimapConnection("bottom_platform", MinimapConnection.FALL_ANY),
        ]
    )
    platform_5_ladder: MinimapFeature = MinimapFeature(
        left=65,
        right=65,
        top=12,
        bottom=25,
        name="platform_5_ladder",
        connections=[
            MinimapConnection("mid_platform", MinimapConnection.JUMP_LEFT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_RIGHT),
        ],
    )
    platform_2_ladder: MinimapFeature = MinimapFeature(
        left=31,
        right=31,
        top=12,
        bottom=25,
        name="platform_2_ladder",
        connections=[
            MinimapConnection("mid_platform", MinimapConnection.JUMP_LEFT),
            MinimapConnection("mid_platform", MinimapConnection.JUMP_RIGHT),
        ],
    )
    left_ladder: MinimapFeature = MinimapFeature(
        left=25,
        right=25,
        top=25,
        bottom=38,
        name="left_ladder",
        connections=[
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_LEFT),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_RIGHT),
        ],
    )
    right_ladder: MinimapFeature = MinimapFeature(
        left=74,
        right=74,
        top=25,
        bottom=38,
        name="right_ladder",
        connections=[
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_LEFT),
            MinimapConnection("bottom_platform", MinimapConnection.JUMP_RIGHT),
        ],
    )

