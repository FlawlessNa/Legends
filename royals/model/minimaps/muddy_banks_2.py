from royals.model.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class MuddyBanks2Minimap(MinimapPathingMechanics):
    map_area_width = 127
    map_area_height = 71
    minimap_speed = 9.531017923423336

    jump_height: int = 9
    jump_distance: int = 12

    teleport_h_dist = 10
    teleport_v_up_dist = 8
    teleport_v_down_dist = 15
    door_spot = [(i, 50) for i in range(25, 35)]

    @property
    def central_node(self) -> tuple[int, int]:
        return int(self.inner_left_rope.center[0]), int(self.inner_left_rope.center[1])

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return [self.main_platform] * 25 + [
            self.top_left_platform,
            self.top_left_platform,
            self.top_right_platform,
            self.top_right_platform,
        ]

    npc_platform: MinimapFeature = MinimapFeature(
        left=60,
        right=72,
        top=32,
        bottom=32,
        name="npc_platform",
    )
    above_npc_platform: MinimapFeature = MinimapFeature(
        left=60,
        right=72,
        top=24,
        bottom=24,
        name="above_npc_platform",
        connections=[
            MinimapConnection(
                "main_platform", MinimapConnection.PORTAL, [(66, 24)], [(71, 50)]
            )
        ],
    )
    top_right_platform: MinimapFeature = MinimapFeature(
        left=74,
        right=114,
        top=30,
        bottom=30,
        name="top_right_platform",
    )
    top_right_step: MinimapFeature = MinimapFeature(
        left=74,
        right=75,
        top=26,
        bottom=26,
        name="top_right_step",
    )
    top_left_step: MinimapFeature = MinimapFeature(
        left=56,
        right=58,
        top=26,
        bottom=26,
        name="top_left_step",
    )
    top_left_platform: MinimapFeature = MinimapFeature(
        left=12,
        right=58,
        top=30,
        bottom=30,
        name="top_left_platform",
    )
    main_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=121,
        top=50,
        bottom=50,
        name="main_platform",
        connections=[
            MinimapConnection(
                "above_npc_platform", MinimapConnection.PORTAL, [(71, 50)], [(66, 24)]
            )
        ],
    )
    outer_right_rope: MinimapFeature = MinimapFeature(
        left=109,
        right=109,
        top=31,
        bottom=49,
        name="outer_right_rope",
    )
    inner_right_rope: MinimapFeature = MinimapFeature(
        left=77,
        right=77,
        top=31,
        bottom=49,
        name="inner_right_rope",
    )
    inner_left_rope: MinimapFeature = MinimapFeature(
        left=53,
        right=53,
        top=31,
        bottom=43,
        name="inner_left_rope",
    )
    outer_left_rope: MinimapFeature = MinimapFeature(
        left=19,
        right=19,
        top=31,
        bottom=49,
        name="outer_left_rope",
    )
    middle_box_platform: MinimapFeature = MinimapFeature(
        left=56,
        right=58,
        top=46,
        bottom=46,
        name="middle_box_platform",
    )
