import cv2
import numpy as np
import os

from paths import ROOT
from royals.game_interface import InGameDynamicVisuals
from royals.utilities import Box, take_screenshot


class Minimap(InGameDynamicVisuals):
    _menu_icon_detection_needle: np.ndarray = cv2.imread(
        os.path.join(
            ROOT,
            "royals/game_interface/detection_images/world_icon.png",
        )
    )
    _self_color = ((34, 238, 255), (136, 255, 255))
    _stranger_color = ((0, 0, 221), (17, 17, 255))
    _party_color = ((0, 119, 255), (0, 153, 255))  # TODO
    _buddy_color = ((1, 1, 1), (0, 0, 0))  # TODO
    _guildie_color = ((1, 1, 1), (0, 0, 0))  # TODO
    _npc_color = ((0, 221, 0), (0, 255, 0))

    _world_icon_left_offset: int = -27
    _world_icon_right_offset: int = -38

    _minimap_title_detection_color = ((1, 1, 1), (0, 0, 0))  # TODO
    _minimap_state_detection_color = ((255, 204, 85), (255, 204, 85))
    _minimap_area_detection_color = ((153, 119, 85), (153, 119, 85))

    _minimap_area_top_offset_partial: int = 21
    _minimap_area_top_offset_full: int = 64

    def __init__(self, handle: int) -> None:
        super().__init__(handle)

    def is_displayed(self) -> bool:
        return self.get_minimap_state() in ["Partial", "Full"]

    def get_minimap_state(self) -> str | None:
        world_icon_box = self._menu_icon_position()
        if world_icon_box:
            detection_box = world_icon_box + Box(
                offset=True,
                left=self._world_icon_left_offset,
                right=self._world_icon_right_offset,
                top=0,
                bottom=0,
            )
            detection_img = take_screenshot(self.handle, detection_box)
            detection_color = cv2.inRange(
                detection_img, *self._minimap_state_detection_color
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
        self, character_type: str
    ) -> list[tuple[float, float]] | None:
        """
        Returns the positions of all characters of a certain type on the minimap.
        :param character_type: Literal {"Self", "Stranger", "Party", "Buddy", "Guildie", "NPC"}
        :return: list of (x, y) coordinates.
        """
        map_area_box = self.get_map_area_box()
        if map_area_box:
            map_area_img = take_screenshot(self.handle, map_area_box)
            color = {
                "Self": self._self_color,
                "Stranger": self._stranger_color,
                "Party": self._party_color,
                "Buddy": self._buddy_color,
                "Guildie": self._guildie_color,
                "Npc": self._npc_color,
            }[character_type.capitalize()]

            detection_img = cv2.inRange(map_area_img, *color)
            contours, _ = cv2.findContours(
                detection_img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            moments = [cv2.moments(contour) for contour in contours]
            result = [
                (m["m10"] / m["m00"], m["m01"] / m["m00"]) for m in moments if m["m00"]
            ]  # Calculate the center of the contour
            if len(result) == 0 and len(contours) >= 1:
                return [tuple(contours[0][0][0])]
            return result

    def get_map_area_box(self) -> Box | None:
        """
        Returns the box of the map area within the minimap.
        Can only be used when the minimap is at least partially displayed.
        :return:
        """
        entire_minimap_box = self._get_entire_minimap_box()
        if entire_minimap_box:
            if self.get_minimap_state() == "Full":
                top_offset = self._minimap_area_top_offset_full
            else:
                top_offset = self._minimap_area_top_offset_partial
            return Box(
                name="Minimap Area",
                left=entire_minimap_box.left,
                right=entire_minimap_box.right,
                top=entire_minimap_box.top + top_offset,
                bottom=entire_minimap_box.bottom,
            )

    def _get_entire_minimap_box(self) -> Box | None:
        """
        Returns the position of the entire minimap on the screen.
        Only works when the minimap is at least partially displayed.
        :return:
        """
        world_icon_box = self._menu_icon_position()
        if world_icon_box:
            # Create a Box to the left of the world icon box up until there are no more white pixels.
            minimap_title_box = Box(
                left=0,
                right=world_icon_box.right,
                top=world_icon_box.top,
                bottom=world_icon_box.bottom,
            )
            minimap_temp_image = take_screenshot(self.handle, minimap_title_box)
            white_pixels = cv2.inRange(
                minimap_temp_image, (255, 255, 255), (255, 255, 255)
            )
            if np.count_nonzero(white_pixels) == 0:
                return
            # Drop the first "column" of white pixels as it is the white border around the minimap, which we don't need.
            # Add 1 because the actual map area is 1 more pixel to the right
            left_border = np.unique(white_pixels.nonzero()[1])[1] + 1

            # For the right border, use the world icon. Also shift by 1 pixel to the right.
            right_border = world_icon_box.right + 1
            top_border = world_icon_box.top

            # Create a kernel representing the white horizontal line at the bottom of the minimap.
            width = right_border - left_border
            kernel = np.ones((1, width), dtype=np.uint8)

            # Temporary image with arbitrary height to detect the minimap bottom line.
            temp_img = take_screenshot(
                self.handle,
                Box(left_border, right_border, top_border, top_border + 300),
            )
            temp_img = cv2.inRange(temp_img, *self._minimap_area_detection_color)
            temp_img = cv2.erode(temp_img, kernel)
            detected_rows = np.unique(temp_img.nonzero()[0])

            # There are always two lines detected below the map area and one above. Keep the first one below.
            # Also, offset by 4-5 pixels
            if self.get_minimap_state() == "Full":
                offset = 6
            else:
                offset = 5
            return Box(
                name="Entire Minimap",
                left=left_border,
                right=right_border,
                top=top_border,
                bottom=top_border + int(detected_rows[-2]) - offset,
            )

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        pass
