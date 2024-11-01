import cv2
import numpy as np
import os
from paths import ROOT
import xml.etree.ElementTree as ET

from ._background import _BackgroundExtractor
from ._footholds import _FootholdExtractor
from ._ladder_rope import _LadderExtractor
from ._life import _LifeExtractor
from ._objects import _ObjectsExtractor
from ._portals import _PortalsExtractor
from ._tiles import _TilesExtractor


class MapParser:
    _ASSETS = os.path.join(ROOT, "royals/assets/game_files/maps")

    def __init__(self, map_name: str):
        self.tree = ET.parse(os.path.join(self._ASSETS, f"{map_name}.xml"))
        self.root = self.tree.getroot()

        self._info_tree = self.root.find(".//imgdir[@name='info']")
        self._bg_tree = self.root.find(".//imgdir[@name='back']")
        self._life_tree = self.root.find(".//imgdir[@name='life']")
        self._foothold_tree = self.root.find(".//imgdir[@name='foothold']")
        self._rope_tree = self.root.find(".//imgdir[@name='ladderRope']")
        self._minimap_tree = self.root.find(".//imgdir[@name='miniMap']")
        self._portal_tree = self.root.find(".//imgdir[@name='portal']")

        self.background = _BackgroundExtractor(self._bg_tree)
        self.life = _LifeExtractor(self._life_tree)
        self.objects = _ObjectsExtractor(self.root)
        self.portals = _PortalsExtractor(self._portal_tree)
        self.tiles = _TilesExtractor(self.root)
        self.footholds = _FootholdExtractor(
            fh_tree=self._foothold_tree,
            object_fh=self.objects.get_footholds(),
            tile_fh=self.tiles.get_footholds(),
        )
        self.ropes = _LadderExtractor(
            rope_tree=self._rope_tree,
            object_ropes=self.objects.get_ropes(),
        )

        # Extract VR coordinates
        self.vr_left = int(self._info_tree.find("int[@name='VRLeft']").get("value"))
        self.vr_top = int(self._info_tree.find("int[@name='VRTop']").get("value"))
        self.vr_right = int(self._info_tree.find("int[@name='VRRight']").get("value"))
        self.vr_bottom = int(self._info_tree.find("int[@name='VRBottom']").get("value"))
        self.vr_width = self.vr_right - self.vr_left
        self.vr_height = self.vr_bottom - self.vr_top

        # Extract minimap section
        self.mini_vr_w = int(self._minimap_tree.find("int[@name='width']").get("value"))
        self.mini_vr_h = int(self._minimap_tree.find("int[@name='height']").get("value"))
        self.mini_cx = int(self._minimap_tree.find("int[@name='centerX']").get("value"))
        self.mini_cy = int(self._minimap_tree.find("int[@name='centerY']").get("value"))
        self.mini_cv_w = int(
            self._minimap_tree.find("canvas[@name='canvas']").get("width")
        )
        self.mini_cv_h = int(
            self._minimap_tree.find("canvas[@name='canvas']").get("height")
        )
        self.minimap_scale_x = self.mini_vr_w / self.mini_cv_w
        self.minimap_scale_y = self.mini_vr_h / self.mini_cv_h

    def get_raw_minimap_grid(self, binary_mode: bool = False) -> np.ndarray:
        """
        Draws footholds, ropes and portals on a minimap grid.
        If binary_mode is True, the grid will be binary (0 or 255).
        Otherwise,
            - Regular footholds are (255, 255, 255) (white)
            - Footholds from tiles are (255, 0, 0) (blue)
            - Footholds from objects are (0, 255, 0) (green)
            - Portals are (0, 0, 255) (red)
            - Regular Ropes are (255, 255, 0) (yellow)
            - Ropes from objects are (0, 255, 255) (cyan)
        """
        if binary_mode:
            canvas = np.zeros((self.mini_vr_h, self.mini_vr_w), np.uint8)
            mini_canvas = np.zeros((self.mini_cv_h, self.mini_cv_w), np.uint8)
            comparator = 0
        else:
            canvas = np.zeros((self.mini_vr_h, self.mini_vr_w, 3), np.uint8)
            mini_canvas = np.zeros((self.mini_cv_h, self.mini_cv_w, 3), np.uint8)
            comparator = (0, 0, 0)

        self._draw_lines(canvas, self.footholds.res, (255, 255, 255))
        self._draw_lines(canvas, self.footholds.tile_res, (255, 0, 0))
        self._draw_lines(canvas, self.footholds.object_res, (0, 255, 0))
        self._draw_lines(canvas, self.ropes.res, (255, 255, 0))
        self._draw_lines(canvas, self.ropes.object_res, (0, 255, 255))
        self._draw_circles(canvas, self.portals.res, (0, 0, 255))

        if binary_mode:
            non_zero_idx = np.where(canvas != comparator)
        else:
            non_zero_idx = np.where(~np.all(canvas == comparator, axis=-1))
        small_x = (non_zero_idx[1] / self.minimap_scale_x).astype(int)
        small_y = (non_zero_idx[0] / self.minimap_scale_y).astype(int)
        mini_canvas[small_y, small_x] = canvas[non_zero_idx]

        return mini_canvas

    def get_raw_virtual_grid(self, binary_mode: bool = False) -> np.ndarray:
        """
        Draws footholds, ropes and portals on a virtual grid.
        If binary_mode is True, the grid will be binary (0 or 255).
        Otherwise,
            - Regular footholds are (255, 255, 255) (white)
            - Footholds from tiles are (255, 0, 0) (blue)
            - Footholds from objects are (0, 255, 0) (green)
            - Portals are (0, 0, 255) (red)
            - Regular Ropes are (255, 255, 0) (yellow)
            - Ropes from objects are (0, 255, 255) (cyan)
        """
        if binary_mode:
            canvas = np.zeros((self.vr_height, self.vr_width), np.uint8)
        else:
            canvas = np.zeros((self.vr_height, self.vr_width, 3), np.uint8)

        self._draw_lines(canvas, self.footholds.res, (255, 255, 255))
        self._draw_lines(canvas, self.footholds.tile_res, (255, 0, 0))
        self._draw_lines(canvas, self.footholds.object_res, (0, 255, 0))
        self._draw_lines(canvas, self.ropes.res, (255, 255, 0))
        self._draw_lines(canvas, self.ropes.object_res, (0, 255, 255))
        self._draw_circles(canvas, self.portals.res, (0, 0, 255))

        return canvas

    def get_raw_virtual_map(self) -> np.ndarray:
        vr_canvas = np.zeros((self.vr_height, self.vr_width, 4), np.uint8)
        breakpoint()

    def _draw_lines(self, canvas: np.ndarray, lines: list, color: tuple) -> None:
        offset_x, offset_y = self._get_offsets_from_canvas(canvas)
        if len(canvas.shape) == 2:
            color = (255, )
        for line in lines:
            x, y = line['x'], line['y']
            for i in range(0, len(x) - 1):
                cv2.line(
                    canvas,
                    (x[i] + offset_x, y[i] + offset_y),
                    (x[i + 1] + offset_x, y[i + 1] + offset_y),
                    color,
                    1
                )

    def _draw_circles(self, canvas: np.ndarray, circles: list, color: tuple) -> None:
        offset_x, offset_y = self._get_offsets_from_canvas(canvas)
        if len(canvas.shape) == 2:
            color = (255 // 2, )
        for circle in circles:
            x, y = circle['x'], circle['y']
            cv2.circle(
                canvas,
                (x + offset_x, y + offset_y),
                3,
                color,
                -1
            )

    def _get_offsets_from_canvas(self, canvas: np.ndarray) -> tuple:
        h, w = canvas.shape[:2]
        if (h, w) == (self.mini_vr_h, self.mini_vr_w):
            return self.mini_cx, self.mini_cy
        elif (h, w) == (self.vr_height, self.vr_width):
            return -self.vr_left, -self.vr_top

    def draw_vr_canvas(self):
        self._draw_objs()
        self._draw_tiles()
        all_items = self.objects + self.tiles
        all_items.sort(
            key=lambda item: (
                item['Layer'],
                item['z'] if item['Type'] == 'Object' else item['zM'],
                item['zM'] if item['Type'] == 'Object' else item['z'],
                item['ID']
            )
        )

        for item in all_items:
            type_ = item['Type']
            section = item['Section']
            order = item['Order']
            id_ = item['ID']
            desc = item['Desc']
            image = item['Image']
            x = item['x']
            y = item['y']
            f = item['f']
            zM = item['zM']
            z = item['z']
            fh = item['footholds']
            self.paste_image(self.vr_canvas, image, x, y, f, zM, r=0)
            if fh is not None:
                for i in range(0, len(fh) - 1):
                    cv2.line(self.vr_canvas, fh[i], fh[i + 1], (255, 255, 255), 3)

            # print(desc, f"Type={type_}, Section={section}, Order={order}, ID={id_}, x={x}, y={y}, z={z}, zM={zM}, f={f}")
                cv2.imshow("VR Canvas", cv2.resize(self.vr_canvas, None, fx=0.5, fy=0.5))
                cv2.waitKey(0)
        self._draw_footholds()
        self._draw_portals()
        self._draw_ropes()

    def paste_image(self, canvas, image, x, y, f, zM, r):
        if f == 1:
            image = cv2.flip(image, 1)

        h, w = image.shape[:2]
        alpha_s = image[:, :, 3] / 255.0
        alpha_l = 1.0 - alpha_s
        x_start = max(x, 0)
        y_start = max(y, 0)
        x_end = min(x + w, self.vr_width)
        y_end = min(y + h, self.vr_height)

        image_x_start = x_start - x
        image_y_start = y_start - y
        image_x_end = image_x_start + (x_end - x_start)
        image_y_end = image_y_start + (y_end - y_start)

        if r != 0:
            breakpoint()

        for c in range(0, 3):
            canvas[y_start:y_end, x_start:x_end, c] = (
                alpha_s[image_y_start:image_y_end, image_x_start:image_x_end]
                * image[image_y_start:image_y_end, image_x_start:image_x_end, c]
                + alpha_l[image_y_start:image_y_end, image_x_start:image_x_end]
                * canvas[y_start:y_end, x_start:x_end, c]
            )

    def get_approx_vr_coord_from_minimap(
        self, minimap_position: tuple[int, int]
    ) -> tuple[float, float, float, float]:
        """
        Based on current minimap position, returns a bounding box, in VR coordinates,
        of the character's possible location.
        :return: x1, y1, x2, y2
        """
        cx, cy = minimap_position
        min_vr_x = (cx - 0.5) * self.minimap_scale_x
        max_vr_x = (cx + 0.5) * self.minimap_scale_x
        min_vr_y = (cy - 0.5) * self.minimap_scale_y
        max_vr_y = (cy + 0.5) * self.minimap_scale_y
        return min_vr_x, min_vr_y, max_vr_x, max_vr_y

    def get_vr_coord_from_on_screen_position(
        self, on_screen_position: tuple[int, int]
    ) -> tuple[float, float]:
        """
        Based on current on-screen position, returns the VR coordinates.
        To do so, we need to find any object/tile on-screen and extract their known VR
        coordinates. From there, we calculate the distance of the object with the
        character, and we infer the character's VR coordinates.
        """
        pass
