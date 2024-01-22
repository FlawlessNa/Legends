import numpy as np
import time
from dataclasses import dataclass, field
from functools import partial

from botting.core import GameData
from botting.utilities import take_screenshot, Box
from royals.models_implementations.mechanics import MinimapPathingMechanics


@dataclass
class AntiDetectionData(GameData):
    shut_down_at: float = field(default=None, repr=False, init=False)
    current_minimap: MinimapPathingMechanics = field(repr=False, default=None)
    current_minimap_area_box: Box = field(repr=False, init=False)
    current_entire_minimap_box: Box = field(repr=False, init=False)
    minimap_title_img: np.ndarray = field(repr=False, init=False)
    mob_check_last_detection: float = field(repr=False, init=False)

    @property
    def args_dict(self) -> dict[str, callable]:
        return {
            "mob_check_last_detection": time.perf_counter,
            "current_minimap_area_box": partial(
                self.current_minimap.get_map_area_box, self.handle
            ),
            "current_entire_minimap_box": partial(
                self.current_minimap.get_entire_minimap_box, self.handle
            ),
            **super().args_dict,
        }

    def _get_minimap_title_img(self):
        return take_screenshot(
            self.handle, self.current_minimap.get_minimap_title_box(self.handle)
        )
