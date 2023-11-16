import cv2
import numpy as np
import time

from abc import ABC, abstractmethod

from botting.visuals import InGameBaseVisuals


class ChatLine(InGameBaseVisuals, ABC):
    """
    Base class for all chat lines. Contains a class method allowing to instantiate the proper
    chat line class based on the image.
    Timestamp is created upon instantiation.
    """

    all_chat_types = frozenset(
        {
            "General",
            "GM",
            "Whisper",
            "Gachapon",
            "ItemSmega",
            "TVSmega",
            "Smega",
            "Alliance",
            "Party",
            "Guild",
            "Megaphone",
            "Buddy",
            "Spouse",
            "Notice",
            "MapleTip",
            "Warning",
            "System",
        }
    )
    chat_color: tuple[tuple, tuple]

    def __init__(self, chat_line_img: np.ndarray) -> None:
        self.image = chat_line_img
        self._timestamp = time.ctime()
        self.text = self.read_text()
        self.author = self.get_author()

    def __repr__(self) -> str:
        return f"{self.name}({self.author}:{self.text})"

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @staticmethod
    def from_img(chat_line_img: np.ndarray) -> "ChatLine":
        # Skip first rows of pixels in the line, because some characters of the previous line may be present (the "@" does so).
        # Skip right-hand side of the image, as sometimes login or cc notifications can mess up line type recognition.
        img = chat_line_img[2: , 0:350]
        detected_types = set()
        for chat_type in ChatLine.all_chat_types:
            if InGameBaseVisuals._color_detection(
                img, eval(chat_type).chat_color, pixel_threshold=10
            ):
                detected_types.add(eval(chat_type))

        # Color used for Item Smega is also visible in Gachapon lines, so remove Item Smega if Gachapon is detected.
        # if detected_types == {ItemSmega, Gachapon}:
        #     detected_types.remove(ItemSmega)

        # Smega lines do contain the color of General lines, so remove General if Smega is detected.
        if (
            detected_types == {Smega, General}
            or detected_types == {TVSmega, General}
            or detected_types == {ItemSmega, General}
        ):
            detected_types.remove(General)

        if len(detected_types) == 1:
            chat_class = detected_types.pop()
            chat_instance = chat_class(chat_line_img)
            return chat_instance

        else:
            cv2.imshow(f"Multi Lines Recognized {detected_types}", chat_line_img)
            cv2.waitKey(1)
            breakpoint()  # TODO - Handle these cases, start by assuming cursor or a menu is overlapping the chat line.

    def read_text(self) -> str:
        return self.read_from_img(self.image, config="--psm 7")

    @property
    def timestamp(self) -> str:
        return self._timestamp

    @abstractmethod
    def get_author(self) -> str:
        pass

    @staticmethod
    def _crop_white_rectangle(image: np.ndarray) -> np.ndarray:
        # Find the largest white rectangle in image and crop it out.
        contours, _ = cv2.findContours(
            cv2.inRange(image, (255, 255, 255), (255, 255, 255)),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE,
        )
        rects = [cv2.boundingRect(contour) for contour in contours]
        widths = [rect[2] for rect in rects]
        largest_rect = rects[widths.index(max(widths))]
        x, y, w, h = largest_rect
        left_part = image[:, :x]
        right_part = image[:, x + w :]
        return np.hstack((left_part, right_part))

    @staticmethod
    def _crop_based_on_contour(image: np.ndarray) -> np.ndarray:
        contours, _ = cv2.findContours(
            image, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        # Sort by x coordinate
        contours = sorted(contours, key=lambda ctr: cv2.boundingRect(ctr)[0])
        distances = []
        for i in range(len(contours) - 1):
            x1, _, w1, _ = cv2.boundingRect(contours[i])
            x2, _, _, _ = cv2.boundingRect(contours[i + 1])
            distances.append(x2 - (x1 + w1))
        distances = np.array(distances)
        threshold = 15
        indices = np.where(distances > threshold)[0]
        if indices.size > 0:
            idx = indices[0]
            x, _, w, _ = cv2.boundingRect(contours[indices[0]])
            return image[:, : x + w]
        return image


class General(ChatLine):
    chat_color = ((255, 255, 255), (255, 255, 255))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        Converts into HSV image and apply filters to try and turn off background while leaving chat intact.
        HSV filter was configured using the hsv_filtering (in utilities-toolkit).
        Crop out the line once no more characters are clearly detected.
        To do so, if the horizontal between contours becomes too large, we assume those are noise and crop out.
        """
        processed_img = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower = np.array([0, 0, 145])  # hMin, sMin, vMin
        upper = np.array([179, 80, 255])  # hMax, sMax, vMax
        processed_img = cv2.inRange(processed_img, lower, upper)
        processed_img = self._crop_based_on_contour(processed_img)
        processed_img = cv2.resize(
            processed_img, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return cv2.GaussianBlur(processed_img, (7, 7), 0)

    def get_author(self) -> str:
        pass


class GM(ChatLine):
    chat_color = ((190, 190, 190), (200, 200, 200))
    # chat_color = ((0, 0, 0), (0, 0, 0))  # Alternative - this works, but requires modifications to ChatLine.from_img

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = cv2.resize(
            image, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class Whisper(ChatLine):
    chat_color = ((0, 255, 0), (0, 255, 0))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        Converts into HSV image and apply filters to try and turn off background while leaving chat intact.
        HSV filter was configured using the hsv_filtering (in utilities-toolkit).
        Crop out the line once no more characters are clearly detected.
        To do so, if the horizontal between contours becomes too large, we assume those are noise and crop out.
        """
        processed_img = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower = np.array([49, 186, 110])  # hMin, sMin, vMin
        upper = np.array([150, 255, 255])  # hMax, sMax, vMax
        processed_img = cv2.inRange(processed_img, lower, upper)
        processed_img = self._crop_based_on_contour(processed_img)
        processed_img = cv2.resize(
            processed_img, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class Gachapon(ChatLine):
    chat_color = ((51, 204, 153), (51, 204, 153))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = cv2.inRange(image, *self.chat_color)
        processed_img = cv2.bitwise_not(processed_img)
        processed_img = cv2.resize(
            processed_img, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class ItemSmega(ChatLine):
    chat_color = ((1, 195, 225), (15, 210, 240))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = self._crop_white_rectangle(image)
        processed_img = cv2.resize(
            processed_img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class TVSmega(ChatLine):
    chat_color = ((238, 136, 255), (238, 136, 255))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = self._crop_white_rectangle(image)
        # processed_img = cv2.inRange(processed_img, (80, 0, 80), (255, 255, 255))
        processed_img = cv2.resize(
            processed_img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class Smega(ChatLine):
    chat_color = ((68, 0, 119), (68, 0, 119))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = self._crop_white_rectangle(image)
        processed_img = cv2.inRange(processed_img, (68, 0, 119), (130, 86, 170))
        processed_img = cv2.resize(
            processed_img, None, fx=2, fy=2, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class Alliance(ChatLine):
    chat_color = ((1, 1, 1), (0, 0, 0))  # TODO

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        breakpoint()

    def get_author(self) -> str:
        pass


class Party(ChatLine):
    chat_color = ((1, 1, 1), (0, 0, 0))  # TODO

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        breakpoint()

    def get_author(self) -> str:
        pass


class Guild(ChatLine):
    chat_color = ((1, 1, 1), (0, 0, 0))  # TODO

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        breakpoint()

    def get_author(self) -> str:
        pass


class Megaphone(ChatLine):
    """Standard, single-channel megaphone lines."""

    chat_color = ((119, 51, 0), (119, 51, 0))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = cv2.resize(
            image, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class Buddy(ChatLine):
    chat_color = ((1, 1, 1), (0, 0, 0))  # TODO

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        breakpoint()

    def get_author(self) -> str:
        pass


class Spouse(ChatLine):
    chat_color = ((1, 1, 1), (0, 0, 0))  # TODO

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        breakpoint()

    def get_author(self) -> str:
        pass


class Notice(ChatLine):
    """Blue lines from GMs, notices, boss completions or events."""

    chat_color = ((255, 204, 102), (255, 204, 102))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        Converts into HSV image and apply filters to remove background noise.
        HSV filter was configured using the hsv_filtering (in utilities-toolkit).
        Crop out the line once no more characters are clearly detected.
        """
        processed_img = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower = np.array([79, 66, 92])  # hMin, sMin, vMin
        upper = np.array([106, 166, 255])  # hMax, sMax, vMax
        processed_img = cv2.inRange(processed_img, lower, upper)
        processed_img = self._crop_based_on_contour(processed_img)
        processed_img = cv2.resize(
            processed_img, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass


class MapleTip(ChatLine):
    """Yellow lines from [RoyalTip]"""

    chat_color = ((0, 255, 255), (0, 255, 255))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = cv2.inRange(image, (0, 130, 90), (40, 255, 255))
        self._crop_based_on_contour(processed_img)
        processed_img = cv2.resize(processed_img, None, fx=2, fy=2)
        return processed_img

    def get_author(self) -> str:
        return "[RoyalTip]"


class Warning(ChatLine):
    """Red/pink-ish lines appearing when out of potions, unfinished cooldowns, etc."""

    chat_color = ((170, 170, 255), (170, 170, 255))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = cv2.inRange(image, (55, 65, 105), (170, 170, 255))
        processed_img = self._crop_based_on_contour(processed_img)
        processed_img = cv2.resize(
            processed_img, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC
        )
        return processed_img

    def get_author(self) -> str:
        pass


class System(ChatLine):
    """Gray-ish lines appearing upon quest completions, some purchases, etc."""

    chat_color = ((187, 187, 187), (187, 187, 187))

    def __init__(self, img: np.ndarray):
        super().__init__(img)

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        processed_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        processed_img = cv2.inRange(processed_img, 60, 255)
        processed_img = self._crop_based_on_contour(processed_img)
        processed_img = cv2.resize(
            image, None, fx=3, fy=3, interpolation=cv2.INTER_LINEAR
        )
        return processed_img

    def get_author(self) -> str:
        pass
