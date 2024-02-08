from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class LudibriumMinimap(MinimapPathingMechanics):
    map_area_width = 210
    map_area_height = 101
    minimap_speed: float = 8.5  # TODO
    jump_height: int = 5  # TODO
    jump_distance: int = 7  # TODO
    teleport_h_dist = 10
    teleport_v_up_dist = 8
    teleport_v_down_dist = 15
    npc_shop = (76, 74)

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return []

    @property
    def door_spot(self) -> tuple[int, int]:
        return 105, 82

    main_platform: MinimapFeature = MinimapFeature(
        left=5,
        right=202,
        top=82,
        bottom=82,
        name="main_platform",
    )

    ladder_to_patricia = MinimapFeature(
        left=72,
        right=72,
        top=76,
        bottom=81,
        name="ladder_to_patricia"
    )

    patricia_platform1 = MinimapFeature(
        left=70,
        right=83,
        top=75,
        bottom=75,
        name="patricia_platform1"
    )
    patricia_platform2 = MinimapFeature(
        left=70,
        right=83,
        top=74,
        bottom=74,
        name="patricia_platform2"
    )
