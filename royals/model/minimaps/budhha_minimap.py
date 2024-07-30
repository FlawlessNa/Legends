from royals.model.mechanics import (
    MinimapFeature,
    MinimapPathingMechanics,
)


class BuddhaMinimap(MinimapPathingMechanics):
    map_area_width = 194
    map_area_height = 55

    full_map_area_left_offset = 1
    full_map_area_right_offset = 2

    # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    minimap_speed: float = 7.5
    jump_height: int = 5
    jump_distance: int = 5

    teleport_h_dist = 9
    teleport_v_up_dist = 5
    teleport_v_down_dist = 9

    @property
    def feature_cycle(self) -> list[MinimapFeature]:
        return [
            self.main_platform,
        ]

    main_platform: MinimapFeature = MinimapFeature(
        left=9, right=184, top=35, bottom=35, name="main_platform"
    )
