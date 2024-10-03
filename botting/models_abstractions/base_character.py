import numpy as np

from abc import ABC, abstractmethod
from typing import Sequence

from .base_skill import Skill
from botting.visuals import InGameDetectionVisuals


class BaseCharacter(InGameDetectionVisuals, ABC):
    """
    Base class for all characters.
    Should be used to define general detection methods used for on-screen
     character detection.
    Should also define anything related to the character (skills, buffs, etc.).
    The detection_box should be sufficiently large such
     that the character is always within it.
    """
    skills: dict[str, Skill]

    def __init__(
        self, ign: str, *args, **kwargs
    ) -> None:
        super().__init__()
        self.ign = ign

    @abstractmethod
    def get_onscreen_position(self, image: np.ndarray | None) -> Sequence[int] | None:
        pass
