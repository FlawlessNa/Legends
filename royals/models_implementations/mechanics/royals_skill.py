import cv2
import numpy as np
import os
from dataclasses import dataclass, field

from paths import ROOT
from botting.models_abstractions import Skill


@dataclass(frozen=True)
class RoyalsSkill(Skill):
    """
    Adds an icon property to the Skill class, which is used to detect if skill cast
    was successful. Only applies for Buff-type skills.
    """

    icon_path: str = field(
        init=False,
        repr=False,
        default=os.path.join(ROOT, f"royals/assets/detection_images"),
    )

    @property
    def icon(self) -> np.ndarray:
        return cv2.imread(os.path.join(self.icon_path, f"{self.name}.png"))
