import xml.etree.ElementTree as ET


class _LadderExtractor:
    def __init__(
        self,
        rope_tree: ET.Element,
        object_ropes: list[dict] = None,
    ):
        self.tree = rope_tree
        self.res = self.extract_all()
        self.object_res = [{**dct, 'Type': 'Ladder'} for dct in (object_ropes or [])]

    def extract_all(self) -> list:
        """
        Extracts all ropes/ladders from the map .xml file.
        Additional ropes/ladders may be added later on by the tile and object parsers.
        https://mapleref.fandom.com/wiki/Ladders
        l - Whether the ladderRope is a ladder (1) or a rope (0)
        page - The depth of the player when they are on the ladderRope
        uf - Whether the player can climb off the top of the ladderRope
        """
        res = []
        for rope in self.tree:
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
                    'uf': data['uf'],
                    'Type': 'Ladder'
                }
            )
        return res