from botting.models_abstractions import Skill
from .character import Character


class Rogue(Character):
    main_stat = "LUK"

    @property
    def skills(self) -> dict[str, Skill]:
        return {

        }

    def __init__(self, ign: str, detection_configs: str, client_size: str) -> None:
        super().__init__(ign, detection_configs, client_size)