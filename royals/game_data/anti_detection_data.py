import numpy as np
import time
from dataclasses import dataclass, field
from functools import partial

from botting.core import GameData
from botting.utilities import take_screenshot
from royals.models_implementations.mechanics import MinimapPathingMechanics


@dataclass
class AntiDetectionData(GameData):
    shut_down_at: float = field(default=None, repr=False, init=False)
    latest_client_img: np.ndarray = field(repr=False, init=False)
    current_minimap: MinimapPathingMechanics = field(repr=False, default=None)
    minimap_title_img: np.ndarray = field(repr=False, init=False)
    mob_check_last_detection: float = field(repr=False, init=False)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            'latest_client_img': partial(take_screenshot, self.handle),
            'mob_check_last_detection': time.perf_counter,
            **super().args_dict
        }

    def _get_minimap_title_img(self):
        return take_screenshot(self.handle, self.current_minimap.get_minimap_title_box(self.handle))