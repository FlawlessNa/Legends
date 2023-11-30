from royals.model.minimaps.ludi_free_market_template import LudiFreeMarketTemplate
import numpy as np
from botting.utilities import take_screenshot
import cv2
from royals.model.mechanics import generate_grid_template
from pathfinding.core.grid import Grid
from pathfinding.finder.a_star import AStarFinder


HANDLE = 0x002E05E6

if __name__ == "__main__":
    ludi = LudiFreeMarketTemplate()

    map_area = ludi.get_map_area_box(HANDLE)
    while True:
        print(ludi.get_character_positions(HANDLE, "NPC", map_area_box=map_area))
    canvas = np.zeros((map_area.height, map_area.width), dtype=np.uint8)
    canvas = ludi.preprocess_for_grid(canvas)
    grid = generate_grid_template(HANDLE, ludi)
    finder = AStarFinder()
    while True:
        current_pos = ludi.get_character_positions(HANDLE).pop()
        target_pos = ludi.random_point()
        start = grid.node(int(current_pos[0]), int(current_pos[1]))
        end = grid.node(target_pos[0], target_pos[1])
        path, runs = finder.find_path(start, end, grid)

        path_img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
        cv2.drawMarker(path_img, (start.x, start.y), (0, 0, 255), cv2.MARKER_CROSS, markerSize=3)
        cv2.drawMarker(path_img, (end.x, end.y), (255, 0, 0), cv2.MARKER_CROSS, markerSize=3)
        for node in path:
            path_img[node.y, node.x] = (0, 255, 0)
        path_img = cv2.resize(path_img, None, fx=10, fy=10)
        cv2.imshow('test', path_img)
        cv2.waitKey(1)
        grid.cleanup()
        breakpoint()
