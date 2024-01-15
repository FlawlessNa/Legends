import time
from dataclasses import dataclass, field
from functools import partial

from botting.core import GameData
from botting.utilities import Box, CLIENT_HORIZONTAL_MARGIN_PX, CLIENT_VERTICAL_MARGIN_PX
from botting.models_abstractions import Skill
from royals.characters import Character
from royals.maps import RoyalsMap
from royals.models_implementations.mechanics import (
    MinimapPathingMechanics,
    MinimapFeature
)


@dataclass
class RotationData(GameData):
    """ """
    character: Character = field(default=None)
    current_map: RoyalsMap = field(default=None)
    current_minimap: MinimapPathingMechanics = field(repr=False, default=None)
    current_minimap_area_box: Box = field(repr=False, init=False)
    current_entire_minimap_box: Box = field(repr=False, init=False)
    current_minimap_position: tuple[int, int] = field(repr=False, init=False)
    current_minimap_feature: MinimapFeature = field(repr=False, init=False)
    current_on_screen_position: tuple[int, int] = field(repr=False, init=False)
    allow_teleport: bool = False
    last_mob_detection: float = field(repr=False, init=False)
    last_cast: float = field(repr=False, init=False)
    next_target: tuple[int, int] = field(repr=False, init=False)
    next_feature: MinimapFeature = field(repr=False, init=False)
    character_in_a_ladder: bool = field(repr=False, init=False)
    last_position_change: float = field(repr=False, init=False)

    def __post_init__(self):
        if hasattr(self, 'current_map'):
            self.current_minimap = self.current_map.minimap
            self.current_mobs = self.current_map.mobs

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            "minimap_grid": partial(
                self.current_minimap.generate_grid_template,
                allow_teleport=self.allow_teleport,
            ),
            "current_minimap_area_box": partial(
                self.current_minimap.get_map_area_box,
                self.handle
            ),
            "current_minimap_position": partial(
                self._get_self_position,
            ),
            "current_entire_minimap_box": partial(
                self.current_minimap.get_entire_minimap_box,
                self.handle
            ),
            "current_on_screen_position": self._get_on_screen_pos,
            "last_mob_detection": time.perf_counter,
            "last_cast": time.perf_counter,
            "last_position_change": time.perf_counter,
            **super().args_dict
        }

    def get_skill(self, skill: str) -> Skill:
        return self.character.skills[skill]

    def _get_self_position(self) -> tuple[int, int]:
        new_pos = self.current_minimap.get_character_positions(
            self.handle, map_area_box=self.current_minimap_area_box
        )
        assert len(new_pos) == 1, f"Found {len(new_pos)} positions."
        new_pos = new_pos.pop()

        self.current_minimap_feature = self.current_minimap.get_feature_containing(
            new_pos
        )
        if self.current_minimap_feature is not None:
            self.character_in_a_ladder = self.current_minimap_feature.width == 0
        return new_pos

    def _get_on_screen_pos(self) -> tuple[int, int]:
        hide_minimap_box = Box(
            max(
                0,
                self.current_entire_minimap_box.left
                - CLIENT_HORIZONTAL_MARGIN_PX
                - 5,
            ),
            self.current_entire_minimap_box.right + CLIENT_HORIZONTAL_MARGIN_PX + 5,
            max(
                0,
                self.current_entire_minimap_box.top
                - CLIENT_VERTICAL_MARGIN_PX
                - 10,
            ),
            self.current_entire_minimap_box.bottom + CLIENT_VERTICAL_MARGIN_PX + 5,
        )
        hide_tv_smega_box = Box(left=700, right=1024, top=0, bottom=300)
        return self.character.get_onscreen_position(
            None,
            self.handle,
            [
                hide_minimap_box,
                hide_tv_smega_box,
            ],  # TODO - Add Chat Box as well into hiding
        )