from dataclasses import dataclass, field

from royals.model.characters import Character
from royals._old.game_data import AntiDetectionData, MaintenanceData, RotationData


@dataclass
class RoyalsData(MaintenanceData, RotationData, AntiDetectionData):
    character: Character = field(repr=False, default=None)

    # minimap_is_displayed: bool = field(repr=False, init=False)
    # minimap_state: str = field(repr=False, init=False)
    # current_direction: str = field(default="right", repr=False, init=False)
    # current_minimap_title_img: np.ndarray = field(repr=False, init=False)
    # currently_attacking: bool = field(repr=False, init=False, default=False)

    # ultimate: Skill = field(repr=False, init=False, default=None)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {**super().args_dict}
