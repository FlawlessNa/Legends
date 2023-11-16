import numpy as np

from abc import ABC, abstractmethod
from typing import Sequence

from botting.visuals import InGameBaseVisuals
from botting.utilities import Box


class BaseCharacter(InGameBaseVisuals, ABC):
    """
    Base class for all characters.
    Should be used to define general detection methods used for on-screen character detection.
    Should also define anything related to the character (skills, buffs, etc).
    The detection_box should be sufficiently large such that the character is always within it.
    """

    detection_box: Box

    def __init__(self, skills: list["Skills"] | None = None) -> None:
        self.skills = skills

    @abstractmethod
    def get_character_position(self, image: np.ndarray) -> Sequence[int] | None:
        pass