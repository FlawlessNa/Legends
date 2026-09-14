"""Reading detection images off disk, with a failure you can actually read."""

import cv2
import numpy as np

__all__ = ["read_detection_image"]


def read_detection_image(path: str) -> np.ndarray:
    """
    Load a detection needle, raising if it is not there.

    `cv2.imread` returns `None` for a missing or unreadable file rather than
    raising, and every caller here assigns the result straight to a
    `np.ndarray` class attribute. A typo in an asset path therefore travelled
    as far as the first template match before failing, with nothing naming the
    file. This turns that into an error at import, where the path is still in
    hand.

    :param path: Absolute path to the image.
    :return: The image.
    :raises FileNotFoundError: If OpenCV could not read it.
    """
    image = cv2.imread(path)
    if image is None:
        raise FileNotFoundError(f"Could not read the detection image at {path!r}.")
    return image
