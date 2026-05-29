import xml.etree.ElementTree as ET


class _LifeExtractor:
    def __init__(
        self,
        life_tree: ET.Element,
    ):
        self.tree = life_tree
        self.res = self.extract_all()

    def extract_all(self):
        res = {}
        for section in self.tree:
            section_name = section.attrib["name"]
            type_, id_, x, y, mob_time, f, hide, fh, cy, rx0, rx1 = self._extract_specs(
                section
            )
            key = (id_, type_)
            life_data = res.setdefault(key, [])
            life_data.append(
                {
                    "Layer": section_name,
                    "type": type_,
                    "ID": id_,
                    "x": x,
                    "y": y,
                    "mobTime": mob_time,
                    "f": f,
                    "hide": hide,
                    "fh": fh,
                    "cy": cy,
                    "rx0": rx0,
                    "rx1": rx1,
                }
            )
        return res

    @staticmethod
    def _extract_specs(section: ET.Element) -> tuple:
        type_ = section.find("string[@name='type']").get("value")
        id_ = int(section.find("string[@name='id']").get("value"))
        x = int(section.find("int[@name='x']").get("value"))
        y = int(section.find("int[@name='y']").get("value"))
        mob_time = int(section.find("int[@name='mobTime']").get("value"))
        f = int(section.find("int[@name='f']").get("value"))
        hide = section.find("int[@name='hide']").get("value")
        fh = section.find("int[@name='fh']").get("value")
        cy = int(section.find("int[@name='cy']").get("value"))
        rx0 = int(section.find("int[@name='rx0']").get("value"))
        rx1 = int(section.find("int[@name='rx1']").get("value"))
        return type_, id_, x, y, mob_time, f, hide, fh, cy, rx0, rx1
