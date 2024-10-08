import cv2
import numpy as np
import os
from paths import ROOT
import xml.etree.ElementTree as ET

from royals import royals_ign_finder
from royals.model.interface.dynamic_components.minimap import Minimap
from botting.utilities import client_handler, take_screenshot


class MapParser:
    _ASSETS = os.path.join(ROOT, "royals/assets/game_files/maps")

    def __init__(self, map_name: str):
        self.tree = ET.parse(os.path.join(self._ASSETS, f"{map_name}.xml"))
        self.root = self.tree.getroot()

        self._info_tree = self.root.find(".//imgdir[@name='info']")
        self._minimap_tree = self.root.find(".//imgdir[@name='miniMap']")
        self._foothold_tree = self.root.find(".//imgdir[@name='foothold']")
        self._portal_tree = self.root.find(".//imgdir[@name='portal']")
        self._rope_tree = self.root.find(".//imgdir[@name='ladderRope']")

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

        self.vr_canvas = np.zeros((self.vr_height, self.vr_width, 4), np.uint8)
        self.fh_canvas = np.zeros((self.vr_height, self.vr_width, 3), np.uint8)
        self.mini_vr_canvas = np.zeros((self.mini_vr_h, self.mini_vr_w, 3), np.uint8)
        self.mini_canvas = np.zeros((self.mini_cv_h, self.mini_cv_w, 3), np.uint8)

        self._tiles_images = {}
        self._object_images = {}

        self.footholds = self._extract_all_footholds()
        self.ropes = self._extract_all_ropes()
        self.tiles = self._extract_all_tiles()
        self.objects = self._extract_all_objects()
        self.portals = self._extract_all_portals()

        # Draws lines on the foothold canvas
        self._draw_footholds()
        self._draw_ropes()
        self._draw_portals()

        # Draws lines on the minimap-VR coordinates canvas and actual mini-canvas
        self._draw_minimap()
        # cv2.waitKey(0)

        # Draws everything on the map VR canvas
        # self._draw_map()

    def _extract_all_footholds(self) -> list:
        """
        Extracts all footholds from the map .xml file.
        Additional footholds may be added later on by the tile and object parsers.
        """
        res = []
        for layer_id in self._foothold_tree:
            for fh_group in layer_id:
                for fh in fh_group:
                    data = {
                        elem.attrib['name']: int(elem.attrib['value']) for elem in fh
                    }
                    assert all(
                        key in data for key in ['x1', 'y1', 'x2', 'y2', 'prev', 'next']
                    )
                    res.append(
                        {
                            'x': (data['x1'], data['x2']),
                            'y': (data['y1'], data['y2']),
                            'prev': data['prev'],
                            'next': data['next']
                        }
                    )
        return res

    def _extract_all_ropes(self) -> list:
        """
        Extracts all ropes/ladders from the map .xml file.
        Additional ropes/ladders may be added later on by the tile and object parsers.
        https://mapleref.fandom.com/wiki/Ladders
        l - Whether the ladderRope is a ladder (1) or a rope (0)
        page - The depth of the player when they are on the ladderRope
        uf - Whether the player can climb off the top of the ladderRope
        """
        res = []
        for rope in self._rope_tree:
            data = {
                elem.attrib['name']: int(elem.attrib['value']) for elem in rope
            }
            assert set(data.keys()) == {'x', 'y1', 'y2', 'l', 'page', 'uf'}
            res.append(
                {
                    'x': (data['x'], data['x']),
                    'y': (data['y1'], data['y2']),
                    'l': data['l'],
                    'page': data['page'],
                    'uf': data['uf']
                }
            )
        return res

    def _extract_all_tiles(self) -> dict:
        """
        Parses the map .xml file to extract all tile specifications.
        Also extracts the tiles .png and .xml specifications to get all information.
        Adds any footholds tied to tiles into the footholds list.
        """
        res = {}
        for section in self.root:
            section_name = section.get("name")
            if section_name.isdigit():
                info_section = section.find("imgdir[@name='info']")
                tile_section = section.find("imgdir[@name='tile']")
                for idx, tile in enumerate(tile_section.findall("imgdir")):
                    tS = info_section.find("string[@name='tS']").get("value")
                    u, no, x, y, zM = self._extract_tile_info(tile)

                    image_path = self.get_tile_image_path(tS, u, no)
                    image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                    self._tiles_images.setdefault(image_path, image)

                    tile_data = res.setdefault((tS, u, no), [])
                    xml_path = self.get_tile_xml_path(tS)
                    offset_x, offset_y, z, fh = self._get_tile_data(xml_path, u, no)
                    if fh:
                        self.footholds.append(
                            {
                                'x': tuple(i + x for i in fh['x']),
                                'y': tuple(i + y for i in fh['y'])
                            }
                        )
                    x -= offset_x
                    y -= offset_y
                    tile_data.append(
                        {
                            'Section': section_name,
                            'ID': tile.attrib['name'],
                            'x': x,
                            'y': y,
                            'zM': zM,
                            'z': z,
                            'f': 0,
                            'r': 0,
                        }
                    )
        return res

    def _extract_all_objects(self) -> dict:
        """
        Parses the map .xml file to extract all objects specifications.
        Also extracts the objects .png and .xml specifications to get all information.
        Adds any footholds tied to objects into the footholds list.
        """
        res = {}
        for section in self.root:
            section_name = section.get("name")
            if section_name.isdigit():
                obj_section = section.find("imgdir[@name='obj']")
                for idx, obj in enumerate(obj_section.findall("imgdir")):
                    oS, l0, l1, l2, x, y, z, zM, f, r = self._extract_object_info(obj)

                    image_path = self.get_obj_image_path(oS, l0, l1, l2)
                    image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                    self._object_images.setdefault(image_path, image)

                    object_data = res.setdefault((oS, l0, l1, l2), [])
                    xml_path = self.get_obj_xml_path(oS)
                    offset_x, offset_y, fh, ropes = self._get_obj_data(
                        xml_path, l0, l1, l2
                    )
                    if fh:
                        self.footholds.append(
                            {
                                'x': tuple(i + x for i in fh['x']),
                                'y': tuple(i + y for i in fh['y'])
                            }
                        )
                    if ropes:
                        self.ropes.append(
                            {
                                'x': tuple(i + x for i in ropes['x']),
                                'y': tuple(i + y for i in ropes['y'])
                            }
                        )
                    x -= offset_x
                    y -= offset_y
                    object_data.append(
                        {
                            'Section': section_name,
                            'ID': obj.attrib['name'],
                            'x': x,
                            'y': y,
                            'f': f,
                            'zM': zM,
                            'z': z,
                            'r': r,
                        }
                    )
        return res

    def _extract_all_portals(self) -> list:
        """
        Extracts all portals from the map .xml file, provided they are linked to
        some other portal and not just spawn points.
        https://mapleref.fandom.com/wiki/Portal
        pn: name of the portal (other portals points to a portal by its name)
        pt: type of portal
        tm: target map (ID)
        tn: name of the portal (located in the target map) linked to this portal

        Types of portals:
            - (0, sp) -> Starting Point
            - (1, pi) -> Portal Invisible
            - (2, pv) -> Portal Visible (default portals)
            - (3, pc) -> Portal Collision (invokes whenever it has collision with char)
            - (4, pg) -> Portal Changeable
            - (5, pgi) -> Portal Changeable Invisible
            - (6, tp) -> Town Portal Point (portals created from Mystic Door)
            - (7, ps) -> Portal Script, executes a script when a player enters it
            - (8, psi) -> Portal Script Invisible
            - (9, pcs) -> Portal Collision Script
            - (10, ph) -> Portal Hidden (appears when character is near)
            - (11, psh) -> Portal Script Hidden

        """
        res = []
        for portal in self._portal_tree:
            portal_name = portal.find('string[@name="pn"]').get("value")
            portal_type = portal.find('int[@name="pt"]').get("value")
            if portal_name == 'sp' and portal_type == '0':
                continue
            elif portal_name == 'sp' or portal_type == '0':
                breakpoint()  # This should not happen
            target_map = portal.find('int[@name="tm"]').get("value")
            target_portal = portal.find('string[@name="tn"]').get("value")
            x = int(portal.find('int[@name="x"]').get("value"))
            y = int(portal.find('int[@name="y"]').get("value"))
            res.append(
                {
                    'name': portal_name,
                    'type': portal_type,
                    'target_map': target_map,
                    'target_name': target_portal,
                    'x': x,
                    'y': y
                }
            )
        return res

    @staticmethod
    def _extract_tile_info(tile: ET.Element) -> tuple:
        u = tile.find("string[@name='u']").get("value")
        no = tile.find("int[@name='no']").get("value")
        x = int(tile.find("int[@name='x']").get("value"))
        y = int(tile.find("int[@name='y']").get("value"))
        zM = int(tile.find("int[@name='zM']").get("value"))
        return u, no, x, y, zM

    @staticmethod
    def _extract_object_info(obj: ET.Element) -> tuple:
        oS = obj.find("string[@name='oS']").get("value")
        l0 = obj.find("string[@name='l0']").get("value")
        l1 = obj.find("string[@name='l1']").get("value")
        l2 = obj.find("string[@name='l2']").get("value")
        x = int(obj.find("int[@name='x']").get("value"))
        y = int(obj.find("int[@name='y']").get("value"))
        z = int(obj.find("int[@name='z']").get("value"))
        zM = int(obj.find("int[@name='zM']").get("value"))
        f = int(obj.find("int[@name='f']").get("value"))
        r = int(obj.find("int[@name='r']").get("value"))
        return oS, l0, l1, l2, x, y, z, zM, f, r

    def draw_vr_canvas(self):
        self._draw_objs()
        self._draw_tiles()
        all_items = self.objects + self.tiles
        all_items.sort(
            key=lambda item: (
                item['Section'],
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

    @staticmethod
    def get_obj_image_path(oS, l0, l1, l2):
        return os.path.join(
            MapParser._ASSETS, "images", "objects", oS, f"{l0}.{l1}.{l2}.0.png"
        )

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
    def _get_tile_data(xml_path, u, no) -> tuple:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        section = root.find(f".//imgdir[@name='{u}']")
        subsection = section.find(f".//canvas[@name='{no}']")
        res = subsection.find(".//vector[@name='origin']").attrib
        z = subsection.find("int[@name='z']").attrib['value']
        extended = subsection.find('extended')
        fh = {}
        rope = {}
        if extended is not None and extended.get('name') == 'foothold':
            fh = {
                'x': tuple(int(elem.attrib['x']) for elem in extended.findall('vector')),
                'y': tuple(int(elem.attrib['y']) for elem in extended.findall('vector'))
            }
        elif extended is not None:
            breakpoint()

        return int(res["x"]), int(res["y"]), int(z), fh

    @staticmethod
    def _get_obj_data(xml_path, *args):
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for arg in args:
            root = root.find(f"imgdir[@name='{arg}']")

        root = root.find(f"canvas[@name='0']")
        extended = root.findall('extended')
        assert len(extended) <= 1
        fh = {}
        rope = {}
        if extended and extended[0].get('name') == 'foothold':
            fh = {
                'x': tuple(int(i.attrib['x']) for i in extended[0].findall('vector')),
                'y': tuple(int(i.attrib['y']) for i in extended[0].findall('vector'))
            }
        elif extended and extended[0].get('name') in ['rope', 'ladder']:
            rope = {
                'x': tuple(int(i.attrib['x']) for i in extended[0].findall('vector')),
                'y': tuple(int(i.attrib['y']) for i in extended[0].findall('vector'))
            }
        elif extended:
            breakpoint()
        res = root.find(f"vector[@name='origin']").attrib
        return int(res["x"]), int(res["y"]), fh, rope

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

    def _draw_lines(
        self,
        lines,
        x_offset: int = None,
        y_offset: int = None,
        color = (255, 255, 255),
        show: bool = False
    ) -> None:
        if x_offset is None and y_offset is None:
            target = self.fh_canvas
            x_offset = -self.vr_left
            y_offset = -self.vr_top
            name="Map Lines"
        elif x_offset == self.mini_cx and y_offset == self.mini_cy:
            target = self.mini_vr_canvas
            name="Minimap Lines"
        else:
            raise ValueError("Invalid offsets provided.")

        for line in lines:
            x, y = line['x'], line['y']
            if isinstance(x, int) and isinstance(y, int):
                cv2.circle(target, (x + x_offset, y + y_offset), 1, color, 3)
            else:
                assert len(x) == len(y)
                for i in range(0, len(x) - 1):
                    adj_x1, adj_y1 = x[i] + x_offset, y[i] + y_offset
                    adj_x2, adj_y2 = x[i + 1] + x_offset, y[i + 1] + y_offset
                    cv2.line(
                        target, (adj_x1, adj_y1), (adj_x2, adj_y2), color, 1
                    )
        if show:
            cv2.imshow(name, target)
            cv2.waitKey(1)

    def _draw_footholds(self, show: bool = False):
        self._draw_lines(self.footholds, show=show)

    def _draw_portals(self, show: bool = False):
        self._draw_lines(self.portals, color=(0, 255, 0), show=show)

    def _draw_ropes(self, show: bool = False):
        self._draw_lines(self.ropes, color=(255, 0, 0), show=show)

    def _draw_minimap(self, show: bool = False):
        self._draw_lines(self.footholds, self.mini_cx, self.mini_cy)
        self._draw_lines(
            self.portals, self.mini_cx, self.mini_cy, color=(0, 255, 0)
        )
        self._draw_lines(
            self.ropes, self.mini_cx, self.mini_cy, color=(255, 0, 0)
        )
        non_zero_idx = np.where(~np.all(self.mini_vr_canvas == [0, 0, 0], axis=-1))
        small_x = (non_zero_idx[1] / self.minimap_scale_x).astype(int)
        small_y = (non_zero_idx[0] / self.minimap_scale_y).astype(int)
        self.mini_canvas[small_y, small_x] = self.mini_vr_canvas[non_zero_idx]
        if show:
            cv2.imshow('Minimap', cv2.resize(self.mini_canvas, None, fx=5, fy=5))
            cv2.waitKey(1)

    def create_minimap_py_file(self):
        """
        Creates a .py file which describes all minimap features (as contours??)
        The user can then fine-tune some of these as desired (Ex: higher weights on some
        feature to avoid them as much as possible in pathing algorithm)
        """
        pass

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


if __name__ == "__main__":
    map_name = "MysteriousPath3"
    map_parser = MapParser(map_name)
    orig_mini = cv2.threshold(cv2.cvtColor(map_parser.mini_canvas.copy(), cv2.COLOR_BGR2GRAY), 1, 255, cv2.THRESH_BINARY)[1]
    cnt, _ = cv2.findContours(orig_mini, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    copied = np.zeros(orig_mini.shape, np.uint8)
    cv2.drawContours(copied, cnt, -1, 255, 1)
    cv2.imshow("Contours", cv2.resize(copied, None, fx=5, fy=5))
    cv2.imshow('Orig', cv2.resize(orig_mini, None, fx=5, fy=5))
    print("Equal", np.array_equal(orig_mini, copied))
    cv2.waitKey(0)
    # map_parser.draw_vr_canvas()
    # cv2.imshow("FH Canvas", cv2.resize(map_parser.fh_canvas, None, fx=0.5, fy=0.5))
    # cv2.imshow('Mini VR Canvas', cv2.resize(map_parser.mini_vr_canvas, None, fx=0.5, fy=0.5))
    # cv2.imshow('Mini Canvas', cv2.resize(map_parser.mini_canvas, None, fx=5, fy=5))
    # cv2.waitKey(1)
    # breakpoint()
    HANDLE = client_handler.get_client_handle("StarBase", royals_ign_finder)
    # objects = {
    #     "16": {
    #         "path": r"C:\Users\nassi\Games\MapleRoyals\Legends\royals\assets\game_files\maps\images\acc4\toyCastle2.b2.6.0.png",
    #         "x": -608,
    #         "y": 532,
    #     },
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
    # }

    class FakeMinimap(Minimap):
        map_area_width = map_parser.mini_cv_w
        map_area_height = map_parser.mini_cv_h

        def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
            pass

    minimap = FakeMinimap()
    map_area_box = minimap.get_map_area_box(HANDLE)

    from royals.model.characters import Bishop
    # client_img = take_screenshot(HANDLE)
    # char = Bishop("StarBase", "data/model_runs/character_detection/ClericChronosTraining - Nano120")
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
    # for obj in objects:
    #     x, y = objects[obj]["x"] - map_parser.vr_left, objects[obj]["y"] - map_parser.vr_top
    #     cv2.circle(map_parser.vr_canvas, (x, y), 5, (255, 255, 255), 5)
    while True:
        copied_mini = map_parser.mini_canvas.copy()
        copied_vr_mini = map_parser.mini_vr_canvas.copy()
        pos = minimap.get_character_positions(HANDLE, map_area_box=map_area_box).pop()
        vr_coord = map_parser.get_approx_vr_coord_from_minimap(pos)
        cv2.circle(copied_mini, pos, 1, (0, 255, 0), 1)
        cv2.rectangle(copied_vr_mini, (int(vr_coord[0]), int(vr_coord[1])), (int(vr_coord[2]), int(vr_coord[3])), (0, 0, 255), 1)
        cv2.imshow("Test Pos", cv2.resize(copied_mini, None, fx=5, fy=5))
        cv2.imshow("Test VR", cv2.resize(copied_vr_mini, None, fx=0.5, fy=0.5))
        cv2.waitKey(1)

        # TODO - Try using a new ref point that is not horizontally aligned!
        # copied = map_parser.vr_canvas.copy()
        # client_img = take_screenshot(HANDLE)
        # on_screen_pos = char.get_onscreen_position(client_img, acceptance_threshold=0.5)
        # cv2.rectangle(client_img, (on_screen_pos[0], on_screen_pos[1]),
        #               (on_screen_pos[2], on_screen_pos[3]), 255, 2)
        # cx, cy = (on_screen_pos[0] + on_screen_pos[2]) / 2, (
        #         on_screen_pos[1] + on_screen_pos[3]) / 2
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
        #     cv2.circle(client_img, (center_screen_x, center_screen_y), 5, (0, 255, 0),
        #                -1)
        #     cv2.imshow("Client", client_img)
        #     cv2.waitKey(1)
        # vr_pos = MapParser.map_to_vr_coordinates((cx, cy), ref_pts_screen, ref_pts_vr)
        # cv2.circle(map_parser.vr_canvas, (int(vr_pos[0] - map_parser.vr_left), int(vr_pos[1] - map_parser.vr_top)), 5, (255, 255, 255), 5)
        # # pos = minimap.get_character_positions(HANDLE).pop()
        # # pos = map_parser.translate_to_vr(pos)
        # # cv2.circle(copied, pos, 1, (0, 255, 0), 3)
        # cv2.imshow("Canvas", cv2.resize(copied, None, fx=0.5, fy=0.5))
        # cv2.waitKey(1)
        # # breakpoint()
