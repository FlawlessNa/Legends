from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class KampungVillageMinimap(MinimapPathingMechanics):
    map_area_width = 153
    map_area_height = 87
    minimap_speed: float = 8.5  # TODO
    jump_height: int = 5  # TODO
    jump_distance: int = 7  # TODO
    teleport_h_dist = 10
    teleport_v_up_dist = 7
    teleport_v_down_dist = 15

    # npc_shop = (32, 66)  # Real value returned
    npc_shop = (32, 67)  # Adjusted value to make it on a walkable node

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return []

    @property
    def door_spot(self) -> tuple[int, int]:
        return 84, 24

    right_main_platform: MinimapFeature = MinimapFeature(
        left=96,
        right=146,
        top=67,
        bottom=67,
        name='right_main_platform',
        connections=[
            MinimapConnection(
                'right_upper_portal',
                MinimapConnection.PORTAL,
                [(114, 67)],
                [(91, 32)],
            )
        ]
    )
    right_main_slope: MinimapFeature = MinimapFeature(
        left=90,
        right=96,
        top=67,
        bottom=71,
        name='right_main_slope',
        is_irregular=True,
        backward=True
    )
    center_main_platform: MinimapFeature = MinimapFeature(
        left=62,
        right=90,
        top=71,
        bottom=71,
        name='center_main_platform',
    )
    left_main_slope: MinimapFeature = MinimapFeature(
        left=57,
        right=62,
        top=67,
        bottom=71,
        name='left_main_slope',
        is_irregular=True
    )
    left_main_platform: MinimapFeature = MinimapFeature(
        left=7,
        right=57,
        top=67,
        bottom=67,
        name='left_main_platform',
        connections=[
            MinimapConnection(
                'left_upper_portal',
                MinimapConnection.PORTAL,
                [(40, 67)],
                [(62, 32)],
            ),
        ]
    )
    left_mid_slope: MinimapFeature = MinimapFeature(
        left=42,
        right=54,
        top=58,
        bottom=66,
        name='left_mid_slope',
        is_irregular=True,
        backward=True
    )
    mid_platform: MinimapFeature = MinimapFeature(
        left=54,
        right=99,
        top=58,
        bottom=58,
        name='mid_platform',
        connections=[
            MinimapConnection(
                'house_roof3',
                MinimapConnection.PORTAL,
                [(78, 58)],
                [(76, 35)],
            )
        ]
    )
    right_mid_slope: MinimapFeature = MinimapFeature(
        left=99,
        right=111,
        top=58,
        bottom=66,
        name='right_mid_slope',
        is_irregular=True
    )
    house_roof1: MinimapFeature = MinimapFeature(
        left=70,
        right=85,
        top=33,
        bottom=33,
        name='house_roof1',
    )
    house_roof2: MinimapFeature = MinimapFeature(
        left=70,
        right=85,
        top=34,
        bottom=34,
        name='house_roof2',
    )
    house_roof3: MinimapFeature = MinimapFeature(
        left=70,
        right=85,
        top=35,
        bottom=35,
        name='house_roof3',
        connections=[
            MinimapConnection(
                'mid_platform',
                MinimapConnection.PORTAL,
                [(76, 35)],
                [(78, 58)],
            )
        ]
    )
    house_roof_slope: MinimapFeature = MinimapFeature(
        left=61,
        right=70,
        top=33,
        bottom=45,
        name='house_roof_slope',
        is_irregular=True,
        backward=True
    )
    house_front_upper: MinimapFeature = MinimapFeature(
        left=62,
        right=70,
        top=50,
        bottom=50,
        name='house_front_upper',
    )
    house_front_lower: MinimapFeature = MinimapFeature(
        left=62,
        right=82,
        top=53,
        bottom=53,
        name='house_front_lower',
    )
    right_upper_platform: MinimapFeature = MinimapFeature(
        left=99,
        right=144,
        top=36,
        bottom=36,
        name='right_upper_platform',
    )
    right_upper_slope: MinimapFeature = MinimapFeature(
        left=93,
        right=99,
        top=32,
        bottom=35,
        name='right_upper_slope',
        is_irregular=True,
    )
    right_upper_portal: MinimapFeature = MinimapFeature(
        left=87,
        right=93,
        top=32,
        bottom=32,
        name='right_upper_portal',
        connections=[
            MinimapConnection(
                'right_main_platform',
                MinimapConnection.PORTAL,
                [(91, 32)],
                [(114, 67)],
            )
        ]
    )
    left_upper_portal: MinimapFeature = MinimapFeature(
        left=60,
        right=66,
        top=32,
        bottom=32,
        name='left_upper_portal',
        connections=[
            MinimapConnection(
                'left_main_platform',
                MinimapConnection.PORTAL,
                [(62, 32)],
                [(40, 67)],
            ),

        ]
    )
    left_upper_slope: MinimapFeature = MinimapFeature(
        left=54,
        right=59,
        top=32,
        bottom=36,
        name='left_upper_slope',
        is_irregular=True,
        backward=True
    )
    left_upper_platform: MinimapFeature = MinimapFeature(
        left=8,
        right=54,
        top=36,
        bottom=36,
        name='left_upper_platform',
    )
    fm_platform: MinimapFeature = MinimapFeature(
        left=65,
        right=88,
        top=24,
        bottom=24,
        name='fm_platform',
    )
    right_fm_rope: MinimapFeature = MinimapFeature(
        left=87,
        right=87,
        top=25,
        bottom=31,
        name='right_fm_rope',
    )
    left_fm_rope: MinimapFeature = MinimapFeature(
        left=65,
        right=65,
        top=25,
        bottom=31,
        name='left_fm_rope',
    )
    left_house_right_slope: MinimapFeature = MinimapFeature(
        left=44,
        right=50,
        top=48,
        bottom=54,
        name='left_house_right_slope',
        is_irregular=True,
    )
    left_house_platform: MinimapFeature = MinimapFeature(
        left=32,
        right=44,
        top=48,
        bottom=49,
        name='left_house_platform',
        is_irregular=True
    )
    left_house_left_slope: MinimapFeature = MinimapFeature(
        left=27,
        right=31,
        top=49,
        bottom=54,
        name='left_house_left_slope',
        is_irregular=True,
        backward=True
    )
    left_house_front: MinimapFeature = MinimapFeature(
        left=22,
        right=33,
        top=63,
        bottom=63,
        name='left_house_front',
    )
