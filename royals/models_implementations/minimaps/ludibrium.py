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
