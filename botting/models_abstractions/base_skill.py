from dataclasses import dataclass, field
from functools import lru_cache

from botting.utilities import config_reader


@dataclass(frozen=True)
class Skill:
    name: str
    type: str = field(repr=False)
    duration: int = field(default=0, repr=False)
    unidirectional: bool = field(default=True, repr=False)
    horizontal_minimap_distance: float = field(default=0, repr=False)
    vertical_minimap_distance: float = field(default=0, repr=False)
    horizontal_screen_range: int = field(default=0, repr=False)
    vertical_screen_range: int = field(default=0, repr=False)
    cooldown: int = field(default=0, repr=False)
    animation_time: float = field(default=0, repr=False)
    _use_by_default: bool = field(default=False, repr=False)

    @lru_cache
    def key_bind(self, ign: str) -> str:
        return eval(config_reader("keybindings", ign, "Skill Keys"))[self.name]

    @property
    def use_by_default(self) -> bool:
        return (
            True
            if self.type in ["Buff", "Party Buff"] and self._use_by_default
            else False
        )
