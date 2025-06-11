import numpy as np
import xml.etree.ElementTree as ET


class _FootholdExtractor:
    def __init__(
        self,
        fh_tree: ET.Element,
        object_fh: list[dict] = None,
        tile_fh: list[dict] = None,
    ):
        self.tree = fh_tree
        self.res = self.extract_all()
        self.object_res = [{**dct, 'Type': 'Foothold'} for dct in (object_fh or [])]
        self.tile_res = [{**dct, 'Type': 'Foothold'} for dct in (tile_fh or [])]

    def extract_all(self) -> list[dict]:
        """
        Extracts all footholds from the map .xml file.
        Additional footholds may be added later on by the tile and object parsers.
        """
        res = []
        for layer_id in self.tree:
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
                            'Layer ID': layer_id.attrib['name'],
                            'Group ID': fh_group.attrib['name'],
                            'ID': fh.attrib['name'],
                            'x': (data['x1'], data['x2']),
                            'y': (data['y1'], data['y2']),
                            'prev': data['prev'],
                            'next': data['next'],
                            'Type': 'Foothold',
                        }
                    )
        return res
