from royals.models_implementations.mechanics import (
    MinimapFeature,
    MinimapConnection,
    MinimapPathingMechanics,
)


class MysteriousPath3(MinimapPathingMechanics):
    map_area_width = 254
    map_area_height = 87

    # Computed using speed_calculation.py. Assumes a 100% character speed in-game. Represents Nodes per second.
    minimap_speed: float = 6.9642265749772365
    jump_height: int = 5
    jump_distance: int = 5
    jump_down_limit: int = 30

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
    bot_platform: MinimapFeature = MinimapFeature(
        left=91,
        right=185,
        top=68,
        bottom=68,
        name="bot_platform",
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
