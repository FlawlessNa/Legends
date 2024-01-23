import numpy as np
import time
from dataclasses import dataclass, field
from functools import partial

from royals.game_data.minimap_data import MinimapData
from botting.utilities import take_screenshot, Box
from royals.models_implementations.mechanics import MinimapPathingMechanics


@dataclass
class AntiDetectionData(MinimapData):
    shut_down_at: float = field(default=None, repr=False, init=False)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            **super().args_dict,
        }
