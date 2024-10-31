import cv2
import numpy as np
import os
import xml.etree.ElementTree as ET
from paths import ROOT


class _ObjectsExtractor:
    _ASSETS = os.path.join(ROOT, "royals/assets/game_files/maps")

    def __init__(self, root: ET.Element):
        self.trees = [section for section in root if section.get("name").isdigit()]
        self.images = {}
        self.res = self.extract_all()

    def extract_all(self) -> dict:
        """
        Parses the map .xml file to extract all objects specifications.
        Also extracts the objects .png and .xml specifications to get all information.
        Adds any footholds tied to objects into the footholds list.
        """
        res = {}
        for section in self.trees:
            section_name = section.get("name")
            obj_section = section.find("imgdir[@name='obj']")
            for obj in obj_section.findall("imgdir"):
                oS, l0, l1, l2, x, y, z, zM, f, r = self._extract_object_specs_in_map(
                    obj
                )
                key = (oS, l0, l1, l2)

                image_path = self._get_obj_image_path(*key)
                image = cv2.imread(image_path, cv2.IMREAD_UNCHANGED)
                self.images.setdefault(image_path, image)

                object_data = res.setdefault(key, [])
                x, y, fh, ropes = self._extract_object_specs_general(
                    *key, map_x=x, map_y=y
                )
                object_data.append(
                    {
                        'Layer': section_name,
                        'ID': obj.attrib['name'],
                        'x': x,
                        'y': y,
                        'f': f,
                        'zM': zM,
                        'z': z,
                        'r': r,
                        'footholds': fh,
                        'ropes': ropes,
                    }
                )
        return res

    def get_footholds(self):
        pass

    @staticmethod
    def _extract_object_specs_in_map(obj: ET.Element) -> tuple:
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

    @staticmethod
    def _extract_object_specs_general(oS, *args, map_x, map_y) -> tuple:
        xml_path = _ObjectsExtractor._get_obj_xml_path(oS)
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
                'x': tuple(
                    int(i.attrib['x']) + map_x for i in extended[0].findall('vector')
                ),
                'y': tuple(
                    int(i.attrib['y']) + map_y for i in extended[0].findall('vector')
                )
            }
        elif extended and extended[0].get('name') in ['rope', 'ladder']:
            rope = {
                'x': tuple(
                    int(i.attrib['x']) + map_x for i in extended[0].findall('vector')
                ),
                'y': tuple(
                    int(i.attrib['y']) + map_y for i in extended[0].findall('vector')
                )
            }
        elif extended:
            raise NotImplementedError

        res = root.find(f"vector[@name='origin']").attrib
        return map_x - int(res["x"]), map_y - int(res["y"]), fh, rope

    @classmethod
    def _get_obj_image_path(cls, oS, l0, l1, l2) -> str:
        return os.path.join(
            cls._ASSETS, "images", "objects", oS, f"{l0}.{l1}.{l2}.0.png"
        )

    @classmethod
    def _get_obj_xml_path(cls, oS) -> str:
        return os.path.join(cls._ASSETS, "specs", "objects", f"{oS}.img.xml")