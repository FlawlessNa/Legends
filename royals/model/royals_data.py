from botting.core import GameData
from dataclasses import dataclass, field


@dataclass
class RoyalsData(GameData):
    def update(self, *args, **kwargs) -> None:
        pass
