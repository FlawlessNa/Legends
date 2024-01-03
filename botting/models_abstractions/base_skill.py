from dataclasses import dataclass, field
from functools import lru_cache

from botting.utilities import config_reader


@dataclass(frozen=True)
class Skill:
    name: str
    type: str
    duration: int = field(default=0, repr=False)
    unidirectional: bool = field(default=True, repr=False)
    horizontal_minimap_distance: float = field(default=0, repr=False)
    vertical_minimap_distance: float = field(default=0, repr=False)
    horizontal_screen_range: int = field(default=0, repr=False)
    vertical_screen_range: int = field(default=0, repr=False)
    cooldown: int = field(default=0, repr=False)
    animation_time: float = field(default=0, repr=False)

    @lru_cache
    def key_bind(self, ign: str) -> str:
        return eval(config_reader("keybindings", ign, "Skill Keys"))[self.name]
