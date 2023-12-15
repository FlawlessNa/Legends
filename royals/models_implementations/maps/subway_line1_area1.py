import numpy as np

from botting.models_abstractions import BaseMap
from royals.models_implementations.minimaps import KerningLine1Area1
from royals.models_implementations.mobs import Bubbling


class SubwayLine1Area1(BaseMap):
    def __init__(self):
        super().__init__(KerningLine1Area1(), [Bubbling()], None)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass
