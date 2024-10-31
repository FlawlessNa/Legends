import numpy as np
import xml.etree.ElementTree as ET
from royals.model.mechanics.map_creation.minimap_edits_model import MinimapEdits


class _FootholdExtractor:
    def __init__(self, root: ET.Element):
        self.root = root
        self._foothold_tree = self.root.find(".//imgdir[@name='foothold']")
        self.reg_footholds = self._extract_all_footholds()
        self.tile_footholds = []
        self.obj_footholds = []
        self.foothold_features: list[MinimapEdits] = []

        from collections import defaultdict
        self.graph = defaultdict(list)
        self.visited = set()
        self.groups = []

    @staticmethod
    def draw_fh(canvas: np.ndarray, fh: dict, x_offset: int, y_offset: int):
        x, y = fh['x'], fh['y']
        for i in range(0, len(x) - 1):
            adj_x1, adj_y1 = x[i] + x_offset, y[i] + y_offset
            adj_x2, adj_y2 = x[i + 1] + x_offset, y[i + 1] + y_offset
            cv2.line(canvas, (adj_x1, adj_y1), (adj_x2, adj_y2), (255, ), 1)

    def build_graph(self):
        for i, fh1 in enumerate(self.reg_footholds):
            for j, fh2 in enumerate(self.reg_footholds):
                if i != j and self.are_adjacent(fh1, fh2):
                    self.graph[i].append(j)
                    self.graph[j].append(i)

    def are_adjacent(self, fh1, fh2):
        x1, y1 = fh1['x'], fh1['y']
        x2, y2 = fh2['x'], fh2['y']
        return any(
            (x1[i] == x2[j] and abs(y1[i] - y2[j]) <= 1) or
            (y1[i] == y2[j] and abs(x1[i] - x2[j]) <= 1) or
            (abs(x1[i] - x2[j]) <= 1 and abs(y1[i] - y2[j]) <= 1)
            for i in range(2) for j in range(2)
        )

    def dfs(self, node, group):
        self.visited.add(node)
        group.append(self.reg_footholds[node])
        for neighbor in self.graph[node]:
            if neighbor not in self.visited:
                self.dfs(neighbor, group)

    def find_groups(self):
        self.build_graph()
        for node in range(len(self.reg_footholds)):
            if node not in self.visited:
                group = []
                self.dfs(node, group)
                self.groups.append(group)
        return self.groups

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
