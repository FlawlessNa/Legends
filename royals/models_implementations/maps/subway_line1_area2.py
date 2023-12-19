import numpy as np

from botting.models_abstractions import BaseMap
from royals.models_implementations.minimaps import KerningLine1Area2
from royals.models_implementations.mobs import JrWraith


class SubwayLine1Area2(BaseMap):
    def __init__(self):
        super().__init__(KerningLine1Area2(), [JrWraith()], None)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass
