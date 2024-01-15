from dataclasses import dataclass, field

from royals.characters.character import Character
from royals.game_data import AntiDetectionData, MaintenanceData, RotationData


@dataclass
class RoyalsData(
    MaintenanceData,
    RotationData,
    AntiDetectionData
):
    character: Character = field(repr=False, default=None)

    # minimap_is_displayed: bool = field(repr=False, init=False)
    # minimap_state: str = field(repr=False, init=False)
    # current_direction: str = field(default="right", repr=False, init=False)
    # current_minimap_title_img: np.ndarray = field(repr=False, init=False)
    # current_minimap_area_box: Box = field(repr=False, init=False)
    # current_entire_minimap_box: Box = field(repr=False, init=False)
    # current_minimap_position: tuple[int, int] = field(repr=False, init=False)
    # current_minimap_feature: MinimapFeature = field(repr=False, init=False)
    # currently_attacking: bool = field(repr=False, init=False, default=False)
    # last_cast: float = field(repr=False, init=False, default=0)
    # ultimate: Skill = field(repr=False, init=False, default=None)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            **super().args_dict
        }