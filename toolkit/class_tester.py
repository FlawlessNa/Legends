from royals.model.minimaps.ludi_free_market_template import LudiFreeMarketTemplate
from royals.interface import LargeClientChatFeed

# test = ChatFeed(HANDLE)
from botting.utilities import take_screenshot
import cv2
import numpy as np

HANDLE = 0x00620DFE

if __name__ == "__main__":
    test = LargeClientChatFeed()
    for line in test.parse(HANDLE):
        print(line)
    # ludi = LudiFreeMarketTemplate()
    #
    # image = take_screenshot(HANDLE, ludi.get_map_area_box(HANDLE))
    # image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # canvas = np.zeros_like(image)
    # for feature in ludi.features.values():
    #     rect = np.array([[feature.left, feature.top], [feature.left, feature.bottom],
    #                      [feature.right, feature.bottom], [feature.right, feature.top]])
    #     cv2.fillPoly(canvas, [np.array(rect)], (255, 255, 255))
    #
    # kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    # canvas = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, kernel)
    # current_pos = ludi.get_character_positions(HANDLE).pop()
    # target_pos = ludi.random_point()
    # # canvas = cv2.rectangle(
    # #     canvas,
    # #     (math.floor(current_pos[0]), math.floor(current_pos[1])),
    # #     (math.ceil(current_pos[0]), math.ceil(current_pos[1])),
    # #     (0, 0, 255),
    # #     1,
    # # )
    # # canvas = cv2.rectangle(
    # #     canvas,
    # #     (target_pos[0] - 1, target_pos[1] - 1),
    # #     (target_pos[0] + 1, target_pos[1] + 1),
    # #     (255, 0, 0),
    # #     1,
    # # )
    # # canvas = cv2.resize(canvas, None, fx=3, fy=3)
    #
    # cv2.imshow("test", canvas)
    # cv2.waitKey(0)
    #
    # from pathfinding.core.grid import Grid
    # from pathfinding.finder.a_star import AStarFinder
    # grid = Grid(matrix=canvas)
    # finder = AStarFinder()
    # start = grid.node(int(current_pos[0]), int(current_pos[1]))
    # end = grid.node(target_pos[0], target_pos[1])
    # path, runs = finder.find_path(start, end, grid)
    # breakpoint()

