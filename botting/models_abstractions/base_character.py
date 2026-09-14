from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np

from botting.visuals import InGameDetectionVisuals

from .base_skill import Skill


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

    def __init__(self, ign: str, *args: object, **kwargs: object) -> None:
        super().__init__()
        self.ign = ign

    @abstractmethod
    def get_onscreen_position(
        self, image: np.ndarray | None, handle: int
    ) -> Sequence[int] | None:
        pass
