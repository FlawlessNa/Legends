import cv2
import numpy as np
import os
from paths import ROOT
import xml.etree.ElementTree as ET

from royals import royals_ign_finder
from royals.model.interface.dynamic_components.minimap import Minimap
from botting.utilities import client_handler, take_screenshot


# Strategy:
# 1. Draw on the Minimap Canvas
# 2. Extract character position on minimap, translate into minimap VR coordinates
# 3. subtract minimap_centers to this, then subtract actual VR coordinates
# 4. Draw result on VR canvas

# According to Copilot:
# x: The x-coordinate of the object in the map.
# y: The y-coordinate of the object in the map.
# z: The z-index of the object, which determines the drawing order (higher values are drawn on top of lower values).
# f: The flip value, which indicates whether the object should be flipped horizontally (1 for flipped, 0 for not flipped).
# zM: The zoom multiplier, which scales the object (1 means no scaling, values greater than 1 scale up, and values less than 1 scale down).
# r: The rotation value, which specifies the rotation angle of the object in degrees.


class MapParser:
    _ASSETS = os.path.join(ROOT, "royals/assets/game_files/maps")

    def __init__(self, map_name: str):
        self.tree = ET.parse(os.path.join(self._ASSETS, f"{map_name}.xml"))
        self.root = self.tree.getroot()

        self._info_section = self.root.find(".//imgdir[@name='info']")
        self._minimap_section = self.root.find(".//imgdir[@name='miniMap']")
        self._foothold = self.root.find(".//imgdir[@name='foothold']")
        self._portals = self.root.find(".//imgdir[@name='portal']")
        self._ropes = self.root.find(".//imgdir[@name='ladderRope']")

        # Extract VR coordinates
        self.vr_left = int(
            self._info_section.find("int[@name='VRLeft']").attrib["value"]
        )
        self.vr_top = int(self._info_section.find("int[@name='VRTop']").attrib["value"])
        self.vr_right = int(
            self._info_section.find("int[@name='VRRight']").attrib["value"]
        )
        self.vr_bottom = int(
            self._info_section.find("int[@name='VRBottom']").attrib["value"]
        )
        self.vr_width = self.vr_right - self.vr_left
        self.vr_height = self.vr_bottom - self.vr_top

        # Extract minimap section
        self.minimap_vr_width = int(
            self._minimap_section.find("int[@name='width']").attrib["value"]
        )
        self.minimap_vr_height = int(
            self._minimap_section.find("int[@name='height']").attrib["value"]
        )
        self.minimap_center_x = int(
            self._minimap_section.find("int[@name='centerX']").attrib["value"]
        )
        self.minimap_center_y = int(
            self._minimap_section.find("int[@name='centerY']").attrib["value"]
        )

        self.minimap_canvas_width = int(
            self._minimap_section.find("canvas[@name='canvas']").attrib["width"]
        )
        self.minimap_canvas_height = int(
            self._minimap_section.find("canvas[@name='canvas']").attrib["height"]
        )

        self.vr_canvas = np.zeros((self.vr_height, self.vr_width, 4), dtype=np.uint8)
        self.minimap_canvas = np.zeros(
            (self.minimap_vr_height, self.minimap_vr_width, 3), dtype=np.uint8
        )
        self.minimap_scale_x = self.minimap_vr_width / self.minimap_canvas_width
        self.minimap_scale_y = self.minimap_vr_height / self.minimap_canvas_height

        self.tiles = []
        self.objects = []

    def draw_vr_canvas(self):
        self._draw_objs()
        self._draw_tiles()
        all_items = self.objects + self.tiles
        all_items.sort(key=lambda item: sum(item[-2:]))
        # all_items.sort(key=lambda item: (item[-1], item[-2]))
        for item in all_items:
            _, image, x, y, f, zM, z = item
            self.paste_image(self.vr_canvas, image, x, y, f, zM, r=0)
            # print(f"x={x}, y={y}, z={z}, zM={zM}, f={f}")
            # cv2.imshow("VR Canvas", cv2.resize(self.vr_canvas, None, fx=0.5, fy=0.5))
            # cv2.waitKey(0)
        # self._draw_footholds()
        # self._draw_portals()
        # self._draw_ropes()

    @staticmethod
    def get_obj_image_path(oS, l0, l1, l2):
        return os.path.join(MapParser._ASSETS, "images", "objects", oS, f"{l0}.{l1}.{l2}.0.png")

    @staticmethod
    def get_tile_image_path(tS, u, no):
        return os.path.join(MapParser._ASSETS, "images", "tiles", tS, f"{u}.{no}.png")

    @staticmethod
    def get_tile_xml_path(tS):
        return os.path.join(MapParser._ASSETS, "specs", "tiles", f"{tS}.img.xml")

    @staticmethod
    def get_obj_xml_path(oS):
        return os.path.join(MapParser._ASSETS, "specs", "objects", f"{oS}.img.xml")

    @staticmethod
    def _get_tile_offset(xml_path, u, no):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        # Extract the section that correspond to "u"
        section = root.find(f".//imgdir[@name='{u}']")
        # Then extract the subsection that corresponds to "no"
        subsection = section.find(f".//canvas[@name='{no}']")
        # Lastly, extract the "name" = origin values x and y
        res = subsection.find(".//vector[@name='origin']").attrib

        z = subsection.find("int[@name='z']").attrib['value']
        return int(res["x"]), int(res["y"]), int(z)

    @staticmethod
    def _get_obj_offset(xml_path, *args):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for arg in args:
            root = root.find(f"imgdir[@name='{arg}']")

        root = root.find(f"canvas[@name='0']")
        res = root.find(f"vector[@name='origin']").attrib
        return int(res["x"]), int(res["y"])

    def paste_image(self, canvas, image, x, y, f, zM, r):
        h, w = image.shape[:2]
        alpha_s = image[:, :, 3] / 255.0
        alpha_l = 1.0 - alpha_s

        if f == 1:
            image = cv2.flip(image, 1)
        x_start = max(x, 0)
        y_start = max(y, 0)
        x_end = min(x + w, self.vr_width)
        y_end = min(y + h, self.vr_height)

        image_x_start = x_start - x
        image_y_start = y_start - y
        image_x_end = image_x_start + (x_end - x_start)
        image_y_end = image_y_start + (y_end - y_start)

        for c in range(0, 3):
            canvas[y_start:y_end, x_start:x_end, c] = (
                alpha_s[image_y_start:image_y_end, image_x_start:image_x_end]
                * image[image_y_start:image_y_end, image_x_start:image_x_end, c]
                + alpha_l[image_y_start:image_y_end, image_x_start:image_x_end]
                * canvas[y_start:y_end, x_start:x_end, c]
            )

    def _draw_objs(self):
        for section in self.root:
            section_name = section.get("name")
            if section_name.isdigit():
                obj_section = section.find("imgdir[@name='obj']")
                if obj_section is not None:
                    for obj in obj_section.findall("imgdir"):
                        oS = obj.find("string[@name='oS']").get("value")
                        l0 = obj.find("string[@name='l0']").get("value")
                        l1 = obj.find("string[@name='l1']").get("value")
                        l2 = obj.find("string[@name='l2']").get("value")
                        x = int(obj.find("int[@name='x']").get("value")) - self.vr_left
                        y = int(obj.find("int[@name='y']").get("value")) - self.vr_top
                        f = int(obj.find("int[@name='f']").get("value"))
                        zM = int(obj.find("int[@name='zM']").get("value"))
                        z = int(obj.find("int[@name='z']").get("value"))
                        r = int(obj.find("int[@name='r']").get("value"))
                        image_path = self.get_obj_image_path(oS, l0, l1, l2)
                        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                        xml_path = self.get_obj_xml_path(oS)
                        offset_x, offset_y = self._get_obj_offset(xml_path, l0, l1, l2)
                        x -= offset_x
                        y -= offset_y
                        self.objects.append(('Obj', image, x, y, f, zM, z))
        # self.objects.sort(key=lambda item: sum(item[-2:]))
        # for obj in self.objects:
        #     image, x, y, f, zM, z = obj
        #     self.paste_image(self.vr_canvas, image, x, y, f, zM, r=r)

    def _draw_tiles(self):
        for section in self.root:
            section_name = section.get("name")
            if section_name.isdigit():
                tile_section = section.find("imgdir[@name='tile']")
                if tile_section is not None:
                    for tile in tile_section.findall("imgdir"):
                        info_section = section.find("imgdir[@name='info']")
                        tS = info_section.find("string[@name='tS']").get("value")
                        u = tile.find("string[@name='u']").get("value")
                        no = tile.find("int[@name='no']").get("value")
                        x = int(tile.find("int[@name='x']").get("value")) - self.vr_left
                        y = int(tile.find("int[@name='y']").get("value")) - self.vr_top
                        zM = int(tile.find("int[@name='zM']").get("value"))
                        image_path = self.get_tile_image_path(tS, u, no)
                        xml_path = self.get_tile_xml_path(tS)
                        offset_x, offset_y, z = self._get_tile_offset(xml_path, u, no)
                        x -= offset_x
                        y -= offset_y
                        image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                        self.tiles.append(('Tile', image, x, y, 0, zM, z))
            # self.tiles.sort(key=lambda item: item[-1])
            # for tile in self.tiles:
            #     image, x, y, f, zM, z = tile
            #     self.paste_image(self.vr_canvas, image, x, y, 0, zM, r=0)

    @staticmethod
    def _extract_coordinates(element, attribs: list[str]):
        # Check if the element contains x1, y1, x2, and y2 attributes
        result = []

        def _recursive_extract(element, extraction, attribs):
            for attrib in attribs:
                extraction[attrib] = element.find(f"int[@name='{attrib}']")
            if all(elem is not None for elem in extraction.values()):
                result.append(
                    {
                        **{k: int(v.get("value")) for k, v in extraction.items()},
                        "name": element.attrib["name"],
                    }
                )
            for child in element:
                _recursive_extract(child, extraction, attribs)

        _recursive_extract(element, {}, attribs)
        return result

    def _draw_footholds(self):
        fh_coords = self._extract_coordinates(self._foothold, ["x1", "y1", "x2", "y2"])
        for coord in fh_coords:
            x1, y1 = coord["x1"] - self.vr_left, coord["y1"] - self.vr_top
            x2, y2 = coord["x2"] - self.vr_left, coord["y2"] - self.vr_top
            if (
                x1 > self.vr_canvas.shape[1]
                or x2 > self.vr_canvas.shape[1]
                or y1 > self.vr_canvas.shape[0]
                or y2 > self.vr_canvas.shape[0]
            ):
                breakpoint()
            elif x1 < 0 or x2 < 0 or y1 < 0 or y2 < 0:
                breakpoint()
            cv2.line(self.vr_canvas, (x1, y1), (x2, y2), (255, 255, 255), 3)

    def _draw_portals(self):
        portal_coords = self._extract_coordinates(self._portals, ["x", "y"])
        for coord in portal_coords:
            x, y = coord["x"] - self.vr_left, coord["y"] - self.vr_top
            cv2.circle(self.vr_canvas, (x, y), 1, (0, 255, 0), 5)

    def _draw_ropes(self):
        rope_coords = self._extract_coordinates(self._ropes, ["x", "y1", "y2"])
        for coord in rope_coords:
            x, y1, y2 = (
                coord["x"] - self.vr_left,
                coord["y1"] - self.vr_top,
                coord["y2"] - self.vr_top,
            )
            cv2.line(self.vr_canvas, (x, y1), (x, y2), (0, 0, 255), 3)

    def translate_to_vr(self, pos):
        x, y = pos
        scaled_x, scaled_y = x * self.minimap_scale_x, y * self.minimap_scale_y
        x = int(scaled_x - self.minimap_center_x - self.vr_left)
        y = int(scaled_y - self.minimap_scale_y - self.vr_top)
        return x, y

    @staticmethod
    def are_collinear(points):
        # Convert points to a NumPy array
        points = np.array(points)

        # Check if there are at least 3 points
        if len(points) < 3:
            return True  # Less than 3 points are always collinear

        # Calculate the differences
        x_diff = points[:, 0] - points[0, 0]
        y_diff = points[:, 1] - points[0, 1]

        # Calculate the cross product
        cross_product = np.cross(x_diff, y_diff)

        # If all cross products are zero, points are collinear
        return np.all(cross_product == 0)

    @staticmethod
    def map_to_vr_coordinates(screen_pos, reference_points_screen, reference_points_vr):
        """
        # TODO - > test this properly??
        # Only works if points are not collinear
        Maps screen coordinates to VR coordinates using reference points.

        :param screen_pos: Tuple (x, y) of the character's screen position.
        :param reference_points_screen: List of tuples [(x1, y1), (x2, y2), ...] of screen coordinates of reference points.
        :param reference_points_vr: List of tuples [(vx1, vy1), (vx2, vy2), ...] of VR coordinates of reference points.
        :return: Tuple (vx, vy) of the character's VR coordinates.
        """
        if len(reference_points_screen) == 1:
            dx = screen_pos[0] - reference_points_screen[0][0]
            dy = screen_pos[1] - reference_points_screen[0][1]
            return reference_points_vr[0][0] + dx, reference_points_vr[0][1] + dy
        # Convert to numpy arrays
        screen_points = np.array(reference_points_screen)
        vr_points = np.array(reference_points_vr)

        # Calculate the transformation matrix
        A = np.vstack([screen_points.T, np.ones(len(screen_points))]).T
        transformation_matrix, _, _, _ = np.linalg.lstsq(A, vr_points, rcond=None)

        # Apply the transformation to the character's screen position
        screen_pos_homogeneous = np.array([screen_pos[0], screen_pos[1], 1])
        vr_pos = screen_pos_homogeneous @ transformation_matrix

        return tuple(vr_pos)

        # Alternative to maybe try out?
        #
        # import numpy as np
        #
        # # Reference points
        # screen_coords = np.array([[x1, y1], [x2, y2]])
        # vr_coords = np.array([[X1, Y1], [X2, Y2]])
        #
        # # Calculate the transformation matrix A and translation vector b
        # A = np.linalg.lstsq(screen_coords, vr_coords, rcond=None)[0]
        #
        # # Function to transform on-screen coordinates to VR coordinates
        # def transform_coords(screen_point):
        #     return np.dot(A, screen_point)
        #
        # # Example usage
        # screen_point = np.array([x, y])
        # vr_point = transform_coords(screen_point)
        # print(vr_point)


if __name__ == "__main__":
    map_name = "MysteriousPath3"
    map_parser = MapParser(map_name)
    map_parser.draw_vr_canvas()
    cv2.imshow("VR Canvas", cv2.resize(map_parser.vr_canvas, None, fx=0.5, fy=0.5))
    cv2.waitKey(1)
    breakpoint()
    HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)
    objects = {
        "16": {
            "path": r"C:\Users\nassi\Games\MapleRoyals\Legends\royals\assets\game_files\maps\images\acc4\toyCastle2.b2.6.0.png",
            "x": -608,
            "y": 532,
        },
        # "17": {
        #     "path": r"C:\Users\nassi\Games\MapleRoyals\Legends\royals\assets\game_files\maps\images\acc4\toyCastle2.b2.4.0.png",
        #     "x": -28,
        #     "y": 532,
        # },
        # "14": {
        #     "path": r"C:\Users\nassi\Games\MapleRoyals\Legends\royals\assets\game_files\maps\images\acc4\toyCastle2.b2.1.0.png",
        #     "x": -276,
        #     "y": 292,
        # }
    }

    class FakeMinimap(Minimap):
        map_area_width = map_parser.minimap_canvas_width
        map_area_height = map_parser.minimap_canvas_height

        def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
            pass

    minimap = FakeMinimap()
    map_area_box = minimap.get_map_area_box(HANDLE)

    from royals.model.characters import Bishop
    from botting.utilities import take_screenshot
    # client_img = take_screenshot(HANDLE)
    char = Bishop("StarBase", "data/model_runs/character_detection/ClericChronosTraining - Nano120")
    # on_screen_pos = char.get_onscreen_position(client_img, acceptance_threshold=0.5)
    # cv2.rectangle(client_img, (on_screen_pos[0], on_screen_pos[1]), (on_screen_pos[2], on_screen_pos[3]), 255, 2)
    # cx, cy = (on_screen_pos[0] + on_screen_pos[2]) / 2, (on_screen_pos[1] + on_screen_pos[3]) / 2
    # cv2.circle(client_img, (int(cx), int(cy)), 5, (0, 255, 0), -1)
    # ref_pts_screen = []
    # ref_pts_vr = []
    # for obj in objects:
    #     image = cv2.imread(objects[obj]["path"])
    #     # Match object on client image and draw rectangle
    #     match = cv2.matchTemplate(client_img, image, cv2.TM_CCOEFF_NORMED)
    #     min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match)
    #     top_left = max_loc
    #     bottom_right = (top_left[0] + image.shape[1], top_left[1] + image.shape[0])
    #     center_screen_x = top_left[0] + image.shape[1] // 2
    #     center_screen_y = top_left[1] + image.shape[0] // 2
    #     ref_pts_screen.append((center_screen_x, center_screen_y))
    #     # center_vr_x = objects[obj]["x"] - map_parser.vr_left
    #     # center_vr_y = objects[obj]["y"] - map_parser.vr_top
    #     center_vr_x = objects[obj]["x"]
    #     center_vr_y = objects[obj]["y"]
    #     ref_pts_vr.append((center_vr_x, center_vr_y))
    #     cv2.rectangle(client_img, top_left, bottom_right, 255, 2)
    #     cv2.circle(client_img, (center_screen_x, center_screen_y), 5, (0, 255, 0), -1)
    #     cv2.imshow("Client", client_img)
    #     cv2.waitKey(1)

    # vr_pos = MapParser.map_to_vr_coordinates((cx, cy), ref_pts_screen, ref_pts_vr)
    # cv2.circle(map_parser.vr_canvas, (int(vr_pos[0] - map_parser.vr_left), int(vr_pos[1] - map_parser.vr_top)), 5, (255, 255, 255), 5)
    # Test coordiantes of objects by drawing white on the VR canvas
    for obj in objects:
        x, y = objects[obj]["x"] - map_parser.vr_left, objects[obj]["y"] - map_parser.vr_top
        cv2.circle(map_parser.vr_canvas, (x, y), 5, (255, 255, 255), 5)
    while True:
        # TODO - Try using a new ref point that is not horizontally aligned!
        copied = map_parser.vr_canvas.copy()
        client_img = take_screenshot(HANDLE)
        on_screen_pos = char.get_onscreen_position(client_img, acceptance_threshold=0.5)
        cv2.rectangle(client_img, (on_screen_pos[0], on_screen_pos[1]),
                      (on_screen_pos[2], on_screen_pos[3]), 255, 2)
        cx, cy = (on_screen_pos[0] + on_screen_pos[2]) / 2, (
                on_screen_pos[1] + on_screen_pos[3]) / 2
        cv2.circle(client_img, (int(cx), int(cy)), 5, (0, 255, 0), -1)
        ref_pts_screen = []
        ref_pts_vr = []
        for obj in objects:
            image = cv2.imread(objects[obj]["path"])
            # Match object on client image and draw rectangle
            match = cv2.matchTemplate(client_img, image, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match)
            top_left = max_loc
            bottom_right = (top_left[0] + image.shape[1], top_left[1] + image.shape[0])
            center_screen_x = top_left[0] + image.shape[1] // 2
            center_screen_y = top_left[1] + image.shape[0] // 2
            ref_pts_screen.append((center_screen_x, center_screen_y))
            # center_vr_x = objects[obj]["x"] - map_parser.vr_left
            # center_vr_y = objects[obj]["y"] - map_parser.vr_top
            center_vr_x = objects[obj]["x"]
            center_vr_y = objects[obj]["y"]
            ref_pts_vr.append((center_vr_x, center_vr_y))
            cv2.rectangle(client_img, top_left, bottom_right, 255, 2)
            cv2.circle(client_img, (center_screen_x, center_screen_y), 5, (0, 255, 0),
                       -1)
            cv2.imshow("Client", client_img)
            cv2.waitKey(1)
        vr_pos = MapParser.map_to_vr_coordinates((cx, cy), ref_pts_screen, ref_pts_vr)
        cv2.circle(map_parser.vr_canvas, (int(vr_pos[0] - map_parser.vr_left), int(vr_pos[1] - map_parser.vr_top)), 5, (255, 255, 255), 5)
        # pos = minimap.get_character_positions(HANDLE).pop()
        # pos = map_parser.translate_to_vr(pos)
        # cv2.circle(copied, pos, 1, (0, 255, 0), 3)
        cv2.imshow("Canvas", cv2.resize(copied, None, fx=0.5, fy=0.5))
        cv2.waitKey(1)
        # breakpoint()
