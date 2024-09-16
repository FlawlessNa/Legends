import cv2
import numpy as np
import os
from functools import cached_property
from abc import ABC
from paths import ROOT
from botting.utilities import (
    Box,
    take_screenshot,
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
)
from botting.visuals import InGameDynamicVisuals


class Minimap(InGameDynamicVisuals, ABC):
    """
    Implements the royals in-game minimap.
    This is still an abstraction, since each "map" has their own features which need to be defined in child classes.
    """

    map_area_width: int = NotImplemented  # Subclass responsibility
    map_area_height: int = NotImplemented  # Subclass responsibility
    full_map_area_left_offset: int = NotImplemented  # Subclass responsibility
    full_map_area_right_offset: int = NotImplemented  # Subclass responsibility

    _menu_icon_detection_needle: np.ndarray = cv2.imread(
        os.path.join(
            ROOT,
            "royals/assets/detection_images/world_icon.png",
        )
    )
    _self_color = [((136, 255, 255), (136, 255, 255))]
    _self_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))

    _stranger_color = [
        ((0, 0, 255), (0, 0, 255)),
        ((0, 0, 238), (0, 0, 238)),
        ((0, 0, 221), (0, 0, 221)),
    ]
    _stranger_kernel = cv2.getStructuringElement(cv2.MORPH_CROSS, (5, 5))
    _party_color = [((0, 119, 255), (0, 153, 255))]  # TODO
    _party_kernel = None  # TODO
    _buddy_color = [((1, 1, 1), (0, 0, 0))]  # TODO
    _buddy_kernel = None  # TODO
    _guildie_color = [((1, 1, 1), (0, 0, 0))]  # TODO
    _guildie_kernel = None  # TODO
    _npc_color = [((0, 221, 0), (0, 221, 0))]
    _npc_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 3))

    _menu_icon_left_offset: int = -27
    _menu_icon_right_offset: int = -38

    _minimap_state_detection_color = ((255, 204, 85), (255, 204, 85))
    _minimap_area_detection_color = ((153, 119, 85), (153, 119, 85))

    _minimap_area_top_offset_partial: int = 22
    _minimap_area_top_offset_full: int = 65

    @cached_property
    def _validation_title_img(self) -> np.ndarray:
        return cv2.imread(
            os.path.join(
                ROOT, f"royals/assets/detection_images/{self.__class__.__name__}.png"
            )
        )

    def get_minimap_title_img(self, handle: int) -> np.ndarray:
        region = self.get_minimap_title_box(handle)
        img = take_screenshot(handle, region)
        return img

    def validate_in_map(self, handle: int) -> bool:
        return np.array_equal(
            self.get_minimap_title_img(handle), self._validation_title_img
        )

    @classmethod
    def is_displayed(
        cls,
        handle: int,
        client_img: np.ndarray | None = None,
        world_icon_box: Box | None = None,
    ) -> bool:
        """
        Looks into whether the minimap is either Partially or Fully displayed.
        :param handle: Handle to the client.
        :param client_img: If provided, read from image directly instead of taking new ones.
        :param world_icon_box: If provided, use this box instead of detecting the world icon.
        :return: True if the minimap is either Partially or Fully displayed, False otherwise.
        """
        return cls.get_minimap_state(handle, client_img, world_icon_box) in [
            "Partial",
            "Full",
        ]

    @classmethod
    def get_minimap_state(
        cls,
        handle: int,
        client_img: np.ndarray | None = None,
        world_icon_box: Box | None = None,
    ) -> str | None:
        """
        Returns the state of the minimap. Possible states are Hidden, Partial, or Fully displayed.
        :param handle: Handle to the client.
        :param client_img: If provided, read from image directly instead of taking new ones.
        :param world_icon_box: If provided, use this box instead of detecting the world icon.
        :return:
        """
        if world_icon_box is None:
            world_icon_box = cls._menu_icon_position(handle, client_img)
        if world_icon_box:
            detection_box = world_icon_box + Box(
                offset=True,
                left=cls._menu_icon_left_offset,
                right=cls._menu_icon_right_offset,
                top=0,
                bottom=0,
            )
            if client_img is not None:
                detection_img = detection_box.extract_client_img(client_img)
            else:
                detection_img = take_screenshot(handle, detection_box)
            detection_color = cv2.inRange(
                detection_img, *cls._minimap_state_detection_color
            )
            columns = np.unique(detection_color.nonzero()[1])
            if columns.size > 0:
                leftmost, rightmost = columns[0], columns[-1]
                if rightmost < 10:
                    return "Full"
                elif leftmost > 10:
                    return "Hidden"
                else:
                    return "Partial"

    def get_character_positions(
        self,
        handle: int,
        character_type: str = "Self",
        client_img: np.ndarray | None = None,
        world_icon_box: Box | None = None,
        map_area_box: Box | None = None,
    ) -> list[tuple[int, int]] | None:
        """
        Returns the positions of all characters of a certain type on the minimap.
        :param handle: Handle to the client.
        :param character_type: Literal {"Self", "Stranger", "Party", "Buddy", "Guildie", "NPC"}
        :param client_img: If provided, read from image directly instead of taking new ones.
        :param world_icon_box: If provided, use this box instead of detecting the world icon.
        :param map_area_box: If provided, use map area box directly.
        :return: list of (x, y) coordinates.
        """
        if map_area_box is None:
            map_area_box = self.get_map_area_box(handle, client_img, world_icon_box)
        if map_area_box:
            if client_img is not None:
                map_area_img = map_area_box.extract_client_img(client_img)
            else:
                map_area_img = take_screenshot(handle, map_area_box)
            colors = {
                "Self": self._self_color,
                "Stranger": self._stranger_color,
                "Party": self._party_color,
                "Buddy": self._buddy_color,
                "Guildie": self._guildie_color,
                "Npc": self._npc_color,
            }[character_type.capitalize()]
            kernel = {
                "Self": self._self_kernel,
                "Stranger": self._stranger_kernel,
                "Party": self._party_kernel,
                "Buddy": self._buddy_kernel,
                "Guildie": self._guildie_kernel,
                "Npc": self._npc_kernel,
            }[character_type.capitalize()]

            # Loop over each color and detect it. Combine the results before eroding.
            mask = np.zeros_like(map_area_img[:, :, 0])
            for color in colors:
                detection_img = cv2.inRange(map_area_img, *color)
                mask = cv2.bitwise_or(mask, detection_img)

            eroded_detection = cv2.erode(mask, kernel)
            y_x_list = list(zip(*np.where(eroded_detection == 255)))
            # return [(x, y) for y, x in y_x_list]
            return [(x, y+1) for y, x in y_x_list]

    def get_map_area_box(
        self,
        handle: int,
        client_img: np.ndarray | None = None,
        world_icon_box: Box | None = None,
    ) -> Box | None:
        """
        Returns the box of the map area within the minimap.
        Can only be used when the minimap is at least partially displayed.
        Note: Child classes should always define the expected map_area_width and map_area_height.
        If undefined, an attempt is made to detect those automatically, but this is not guaranteed to work.
        Additionally, it slows down the process since more computations are required.
        :param handle: Handle to the client.
        :param client_img: If provided, read from image directly instead of taking new ones.
        :param world_icon_box: If provided, use this box instead of detecting the world icon.
        :return:
        """
        if client_img is None:
            client_img = take_screenshot(handle)
        if world_icon_box is None:
            world_icon_box = self._menu_icon_position(handle, client_img)

        entire_minimap_box = self.get_entire_minimap_box(
            handle, client_img, world_icon_box
        )
        if entire_minimap_box:
            if self.get_minimap_state(handle, client_img, world_icon_box) == "Full":
                # When minimap is fully displayed, there are extra "vertical bands" outside the actual map area.
                top_offset = self._minimap_area_top_offset_full

                # If width is not defined, manually try to crop the extra "vertical bands" outside the actual map area.
                if isinstance(self.map_area_width, type(NotImplemented)):
                    # temp_img in this case is the actual map area box + the extra bands we try to get rid of
                    temp_img = entire_minimap_box.extract_client_img(
                        client_img, top_offset=top_offset
                    )
                    gray = cv2.cvtColor(temp_img, cv2.COLOR_BGR2GRAY)
                    mean_vertical_intensity = np.mean(gray, axis=0)
                    differences = np.abs(np.diff(mean_vertical_intensity))
                    _THRESHOLD = 100  # If extremities show large differences in brightness, get rid of them
                    extra_columns = np.where(differences > _THRESHOLD)[0]
                    while extra_columns.size <= 1:
                        _THRESHOLD -= 2
                        extra_columns = np.where(differences > _THRESHOLD)[0]
                    if extra_columns.size > 0:
                        left_offset = extra_columns[0] + 1
                        right_offset = -(
                            mean_vertical_intensity.shape[0] - extra_columns[-1] - 1
                        )
                    else:
                        left_offset = right_offset = 0
                else:
                    extra_width = entire_minimap_box.width - self.map_area_width
                    if extra_width % 2 == 0:
                        left_offset = extra_width // 2
                        right_offset = -left_offset
                    else:
                        left_offset = self.full_map_area_left_offset
                        right_offset = -self.full_map_area_right_offset
            else:
                top_offset = self._minimap_area_top_offset_partial
                left_offset = 0
                right_offset = 0
            return Box(
                name="Minimap Area",
                left=entire_minimap_box.left + left_offset,
                right=entire_minimap_box.right + right_offset,
                top=entire_minimap_box.top + top_offset,
                bottom=entire_minimap_box.bottom,
            )

    def get_minimap_title_box(
        self,
        handle: int,
        client_img: np.ndarray | None = None,
        world_icon_box: Box | None = None,
    ) -> Box | None:
        """
        Returns the box of the minimap title.
        Can only be used when the minimap is FULLY displayed.
        :param handle: Handle to the client.
        :param client_img: If provided, read from image directly instead of taking new ones.
        :param world_icon_box: If provided, use this box instead of detecting the world icon.
        :return:
        """
        if client_img is None:
            client_img = take_screenshot(handle)
        if world_icon_box is None:
            world_icon_box = self._menu_icon_position(handle, client_img)
        if self.get_minimap_state(handle, client_img, world_icon_box) != "Full":
            return

        entire_minimap_box = self.get_entire_minimap_box(
            handle, client_img, world_icon_box
        )
        if entire_minimap_box:
            map_area_box = self.get_map_area_box(handle, client_img, world_icon_box)
            return Box(
                name="Minimap Title",
                left=entire_minimap_box.left,
                right=entire_minimap_box.right,
                top=entire_minimap_box.top,
                bottom=map_area_box.top,
            )

    def get_entire_minimap_box(
        self,
        handle: int,
        client_img: np.ndarray | None = None,
        world_icon_box: Box | None = None,
    ) -> Box | None:
        """
        Returns the position of the entire minimap on the screen.
        Only works when the minimap is at least partially displayed.
        :param handle: Handle to the client.
        :param client_img: If provided, read from image directly instead of taking new ones.
        :param world_icon_box: If provided, use this box instead of detecting the world icon.
        :return:
        """
        if client_img is None:
            client_img = take_screenshot(handle)
        if world_icon_box is None:
            world_icon_box = self._menu_icon_position(handle, client_img)

        state = self.get_minimap_state(handle, client_img, world_icon_box)
        if world_icon_box and state in ["Partial", "Full"]:
            # Extract World icon (from top to bottom) and all region at the left of the icon.
            minimap_temp_image = client_img[
                world_icon_box.top
                - CLIENT_VERTICAL_MARGIN_PX : world_icon_box.bottom
                - CLIENT_VERTICAL_MARGIN_PX,
                : world_icon_box.right,
            ].copy()

            # Look for white pixels
            white_pixels = cv2.inRange(
                minimap_temp_image, (255, 255, 255), (255, 255, 255)
            )
            if np.count_nonzero(white_pixels) == 0:
                return

            # Find a "column" with all white pixels, followed by 3 columns with no white pixels. This is the minimap border.
            # From there, find the next "column" of white pixels, which is where the map area starts.
            # Add 1 because the actual map area is 1 more pixel to the right
            full_columns = np.where(np.all(white_pixels == 255, axis=0))[0]
            empty_columns = np.where(np.all(white_pixels == 0, axis=0))[0]
            left_border = None
            for col in full_columns:
                if all(col + i in empty_columns for i in range(1, 4)):
                    map_border = col
                    map_border_idx = np.where(full_columns == map_border)[0][0]
                    left_border = full_columns[map_border_idx + 1] + 1
                    break

            # For the right border, use the world icon. Also shift by 1 pixel to the right.
            right_border = world_icon_box.right + 1
            top_border = world_icon_box.top

            # Create a kernel representing the white horizontal line at the bottom of the minimap.
            width = right_border - left_border
            kernel = np.ones((1, width), dtype=np.uint8)

            # Temporary image with arbitrary height to detect the minimap bottom line.
            temp_img = client_img[
                top_border
                - CLIENT_VERTICAL_MARGIN_PX : top_border
                + 300
                - CLIENT_VERTICAL_MARGIN_PX,
                left_border : right_border - CLIENT_HORIZONTAL_MARGIN_PX,
            ]
            temp_img = cv2.inRange(temp_img, *self._minimap_area_detection_color)
            temp_img = cv2.erode(temp_img, kernel)
            detected_rows = np.unique(temp_img.nonzero()[0])

            # There are always two lines detected below the map area and one above. Keep the first one below.
            # Also, offset by 4-5 pixels
            if state == "Full":
                offset = 6
            else:
                offset = 5
            return Box(
                name="Entire Minimap",
                left=left_border + CLIENT_HORIZONTAL_MARGIN_PX,
                right=right_border,
                top=top_border,
                bottom=top_border + int(detected_rows[-2]) - offset,
            )
