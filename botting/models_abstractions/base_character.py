import numpy as np

from abc import ABC, abstractmethod
from typing import Sequence

from .base_skill import Skill
from botting.visuals import InGameBaseVisuals
from botting.utilities import Box


class BaseCharacter(InGameBaseVisuals, ABC):
    """
    Base class for all characters.
    Should be used to define general detection methods used for on-screen
     character detection.
    Should also define anything related to the character (skills, buffs, etc.).
    The detection_box should be sufficiently large such
     that the character is always within it.
    """

    detection_box: Box
    skills: dict[str, Skill]

    def __init__(self, ign: str, *args, **kwargs) -> None:
        self.ign = ign

    @abstractmethod
    def get_onscreen_position(self, image: np.ndarray | None) -> Sequence[int] | None:
        pass
