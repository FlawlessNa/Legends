from royals.model.mechanics import (
    MinimapFeature,
    MinimapPathingMechanics,
)


class TrendZoneMetropolisMinimap(MinimapPathingMechanics):
    map_area_width = 210
    map_area_height = 107
    minimap_speed: float = 8.5  # TODO
    jump_height: int = 5  # TODO
    jump_distance: int = 7  # TODO
    teleport_h_dist = 10
    teleport_v_up_dist = 9
    teleport_v_down_dist = 15
    # npc_shop = (89, 84)  # Real value returned
    npc_shop = (89, 86)  # Adjusted value to make it on a walkable node

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return []

    @property
    def door_spot(self) -> tuple[int, int]:
        return 82, 75

    main_platform: MinimapFeature = MinimapFeature(
        left=4,
        right=105,
        top=89,
        bottom=89,
        name="main_platform",
    )
    kok_hua_bench: MinimapFeature = MinimapFeature(
        left=83,
        right=91,
        top=86,
        bottom=86,
        name="kok_hua_bench",
    )
    flower_pot: MinimapFeature = MinimapFeature(
        left=96,
        right=105,
        top=84,
        bottom=84,
        name="flower_pot",
    )
    door_platform: MinimapFeature = MinimapFeature(
        left=80,
        right=105,
        top=75,
        bottom=75,
        name="door_platform",
    )

    diag_platform = MinimapFeature(
        left=62,
        right=80,
        top=75,
        bottom=87,
        name="diag_platform",
        is_irregular=True,
        backward=True,
    )
