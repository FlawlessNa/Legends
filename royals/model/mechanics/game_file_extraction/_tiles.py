import cv2
import os
import xml.etree.ElementTree as ET
from paths import ROOT


class _TilesExtractor:
    _ASSETS = os.path.join(ROOT, "royals/assets/game_files/maps")

    def __init__(self, root: ET.Element):
        self.trees = [section for section in root if section.get("name").isdigit()]
        self.images = {}
        self.res = self.extract_all()

    def extract_all(self) -> dict:
        """
        Parses the map .xml file to extract all tile specifications.
        Also extracts the tiles .png and .xml specifications to get all information.
        Adds any footholds tied to tiles into the footholds list.
        """
        res = {}
        for section in self.trees:
            section_name = section.get("name")
            info_section = section.find("imgdir[@name='info']")
            tile_section = section.find("imgdir[@name='tile']")
            for tile in tile_section.findall("imgdir"):
                # Tile data specified within map file
                tS = info_section.find("string[@name='tS']").get("value")
                u, no, x, y, zM = self._extract_tile_specs_in_map(tile)
                key = (tS, u, no)

                image_path = self._get_tile_image_path(*key)
                image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                self.images.setdefault(key, image)

                tile_data = res.setdefault(key, [])
                # Tile data (by tile; regardless of map)
                # x-y are offset by the origin of the object
                x, y, z, fh = self._extract_tile_specs_general(
                    *key, map_x=x, map_y=y
                )
                tile_data.append(
                    {
                        'Layer': section_name,
                        'ID': tile.attrib['name'],
                        'x': x,
                        'y': y,
                        'zM': zM,
                        'z': z,
                        'f': 0,
                        'r': 0,
                        'footholds': fh,
                        'Type': 'Tile'
                    }
                )
        return res

    def get_footholds(self) -> list[dict]:
        return [
            obj['footholds'] for obj_lst in self.res.values() for obj in obj_lst
            if obj['footholds']
        ]

    @staticmethod
    def _extract_tile_specs_in_map(tile: ET.Element) -> tuple:
        u = tile.find("string[@name='u']").get("value")
        no = tile.find("int[@name='no']").get("value")
        x = int(tile.find("int[@name='x']").get("value"))
        y = int(tile.find("int[@name='y']").get("value"))
        zM = int(tile.find("int[@name='zM']").get("value"))
        return u, no, x, y, zM

    @staticmethod
    def _extract_tile_specs_general(tS, u, no, map_x, map_y) -> tuple:
        xml_path = _TilesExtractor._get_tile_xml_path(tS)
        root = ET.parse(xml_path).getroot()
        section = root.find(f".//imgdir[@name='{u}']")
        subsection = section.find(f".//canvas[@name='{no}']")
        extended = subsection.findall('extended')
        assert len(extended) <= 1

        origin = subsection.find(".//vector[@name='origin']").attrib
        z = subsection.find("int[@name='z']").attrib['value']
        fh = {}
        if extended and extended[0].get('name') == 'foothold':
            fh = {
                'x': tuple(
                    int(elem.attrib['x']) + map_x
                    for elem in extended[0].findall('vector')
                ),
                'y': tuple(
                    int(elem.attrib['y']) + map_y
                    for elem in extended[0].findall('vector')
                )
            }
        elif extended:
            raise NotImplementedError

        return map_x - int(origin["x"]), map_y - int(origin["y"]), int(z), fh

    @classmethod
    def _get_tile_image_path(cls, tS, u, no):
        return os.path.join(cls._ASSETS, "images", "tiles", tS, f"{u}.{no}.png")

    @classmethod
    def _get_tile_xml_path(cls, tS):
        return os.path.join(cls._ASSETS, "specs", "tiles", f"{tS}.img.xml")
