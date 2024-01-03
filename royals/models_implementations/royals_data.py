import numpy as np

from dataclasses import dataclass, field

from botting.core import GameData
from botting.utilities import (
    Box,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
)
from royals.characters.character import Character
from royals.models_implementations.mechanics import MinimapPathingMechanics


@dataclass
class RoyalsData(GameData):
    character: Character = field(repr=False, init=False)
    minimap_is_displayed: bool = field(repr=False, init=False)
    minimap_state: str = field(repr=False, init=False)
    current_direction: str = field(default="right", repr=False, init=False)
    current_minimap: MinimapPathingMechanics = field(repr=False, init=False)
    current_minimap_title_img: np.ndarray = field(repr=False, init=False)
    current_minimap_area_box: Box = field(repr=False, init=False)
    current_entire_minimap_box: Box = field(repr=False, init=False)
    current_minimap_position: tuple[int, int] = field(repr=False, init=False)
    current_minimap_feature: Box = field(repr=False, init=False)
    character_in_a_ladder: bool = field(repr=False, init=False, default=False)
    currently_attacking: bool = field(repr=False, init=False, default=False)
    last_mob_detection: float = field(repr=False, init=False, default=0)

    def update(self, *args, **kwargs) -> None:
        direction = kwargs.pop("current_direction", self.current_direction)
        if direction != self.current_direction:
            self.current_direction = kwargs["current_direction"]

        for k, v in kwargs.items():
            assert (
                hasattr(self, k)
                or k in self.__annotations__
                or any(k in base.__annotations__ for base in self.__class__.__bases__)
            ), f"Invalid attribute {k}."
            setattr(self, k, v)

        if "current_minimap_area_box" in args:
            self.current_minimap_area_box = self.current_minimap.get_map_area_box(
                self.handle
            )

        if "current_entire_minimap_box" in args:
            self.current_entire_minimap_box = (
                self.current_minimap.get_entire_minimap_box(self.handle)
            )

        if "current_minimap_position" in args:
            new_pos = self.current_minimap.get_character_positions(
                self.handle, map_area_box=self.current_minimap_area_box
            )
            assert len(new_pos) == 1, f"Found {len(new_pos)} positions."
            self.current_minimap_position = new_pos.pop()
            self.current_minimap_feature = self.current_minimap.get_feature_containing(
                self.current_minimap_position
            )
            if self.current_minimap_feature is not None:
                self.character_in_a_ladder = self.current_minimap_feature.width == 0

        if "current_on_screen_position" in args:
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
            self.current_on_screen_position = self.character.get_onscreen_position(
                None,
                self.handle,
                [
                    hide_minimap_box,
                    hide_tv_smega_box,
                ],  # TODO - Add Chat Box as well into hiding
            )
