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
        self.object_res = object_fh
        self.tile_res = tile_fh

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
                            'next': data['next']
                        }
                    )
        return res


if __name__ == '__main__':
    from royals.model.mechanics.game_file_extraction.map_parser import MapParser
    import cv2

    map_name = "MysteriousPath3"
    map_parser = MapParser(map_name)
    canvas = np.zeros((map_parser.vr_height, map_parser.vr_width), np.uint8)
    copied = canvas.copy()
    x_offset = -map_parser.vr_left
    y_offset = -map_parser.vr_top
    fh_extractor = _FootholdExtractor(map_parser.root)
    test = sorted(
        fh_extractor.reg_footholds,
        key=lambda dct: (int(dct['Layer ID']), int(dct['Group ID']), int(dct['ID']))
    )
    drawn = []
    for fh in test:
        if fh['prev'] != 0:
            continue
        fh_extractor.draw_fh(canvas, fh, x_offset, y_offset)
        drawn.append(fh)
        nxt = fh['next']
        if nxt == 0:
            continue
        next_fh = next(foot for foot in test if int(foot['ID']) == fh['next'])
        while next_fh['next'] != 0:
            fh_extractor.draw_fh(canvas, next_fh, x_offset, y_offset)
            drawn.append(next_fh)
            next_fh = next(foot for foot in test if int(foot['ID']) == next_fh['next'])
        cv2.imshow('footholds', canvas)
        cv2.waitKey(0)

    cv2.imshow('footholds', canvas)
    cv2.waitKey(1)
    # contours, _ = cv2.findContours(canvas, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    # for cnt in contours:
    #     cv2.drawContours(copied, [cnt], -1, (255, ), 1)
    #     cv2.imshow('contours', copied)
    #     cv2.waitKey(0)

    groups = fh_extractor.find_groups()
    for group in groups:
        for fh in group:
            fh_extractor.draw_fh(copied, fh, x_offset, y_offset)
        cv2.imshow('group', copied)
        cv2.waitKey(0)

    print(groups)
