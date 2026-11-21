from abc import ABC, abstractmethod
from collections.abc import Sequence

import numpy as np

from botting.visuals import InGameDetectionVisuals


class BaseCharacter(InGameDetectionVisuals, ABC):
    """
    Base class for all characters.
    Should be used to define general detection methods used for on-screen
     character detection.
    The detection_box should be sufficiently large such
     that the character is always within it.
    """

    def __init__(self, ign: str, *args: object, **kwargs: object) -> None:
        super().__init__()
        self.ign = ign

    @abstractmethod
    def get_onscreen_position(
        self, image: np.ndarray, handle: int
    ) -> Sequence[int] | None:
        pass
