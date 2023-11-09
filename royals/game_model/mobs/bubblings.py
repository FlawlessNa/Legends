import numpy as np

# from .BaseMob import BaseMob
from royals.game_model.mobs.base_mob import BaseMob


class Bubbling(BaseMob):
    _hsv_lower = np.array([101, 48, 153])
    _hsv_upper = np.array([113, 255, 255])
    _minimal_rect_height = 25
    _minimal_rect_area = 350
    _maximal_rect_area = 5000

    @classmethod
    def _preprocess_img(cls, image: np.ndarray) -> np.ndarray:
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        binary = cv2.inRange(hsv, cls._hsv_lower, cls._hsv_upper)
        return binary

    @classmethod
    def _filter(cls, contours: tuple[np.ndarray]) -> filter:
        def cond1(contour):
            return (
                cls._minimal_rect_area
                < cv2.contourArea(contour)
                < cls._maximal_rect_area
            )

        def cond2(contour):
            return cv2.boundingRect(contour)[-1] > cls._minimal_rect_height

        return filter(lambda cnt: cond1(cnt) and cond2(cnt), contours)


if __name__ == "__main__":
    HANDLE = 0x00620DFE
    bubbling = Bubbling(HANDLE)
    import cv2
    from royals.utilities import take_screenshot

    while True:
        img = take_screenshot(HANDLE, bubbling.detection_box)
        rects = bubbling.get_onscreen_mobs(img)
        for rect in rects:
            x, y, w, h = rect
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), thickness=2)
        cv2.imshow("test2", img)
        cv2.waitKey(1)
