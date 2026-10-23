"""
`BaseMob.get_onscreen_mobs` returns x1, y1, x2, y2 on the path without a model
(issue #74), the same shape the detection model path returns.

No real mob takes this path today (`MapleMob` sets both hooks to None), so the
test fixes the contract for a future one. No client and no model is involved.
"""

from collections.abc import Sequence

import cv2
import numpy as np

from botting.models_abstractions.base_mob import BaseMob


class _ContourMob(BaseMob):
    """A mob with no detection model, whose preprocessing draws one known rectangle."""

    def __init__(self) -> None:  # no model lookup
        pass

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed = np.zeros(image.shape[:2], np.uint8)
        # Filled, so the contour's bounding rect is x=10, y=20, w=30, h=40.
        cv2.rectangle(processed, (10, 20), (39, 59), 255, -1)
        return processed

    @classmethod
    def _filter(cls, contours: Sequence[np.ndarray]) -> list[np.ndarray]:
        return list(contours)


def test_the_contour_path_returns_x1_y1_x2_y2() -> None:
    image = np.zeros((100, 100, 3), np.uint8)
    mobs = _ContourMob().get_onscreen_mobs(image, 0, debug=False)
    assert mobs == ((10, 20, 40, 60),)
