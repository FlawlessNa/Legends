"""
Helper script to continuously record minimap positioning and record platform endpoints, portals, ladders, etc. based on key presses.
"""
from royals.game_interface.dynamic_components.minimap import Minimap

if __name__ == "__main__":
    HANDLE = 0x00620DFE
    minimap = Minimap(HANDLE)
    from royals.utilities import take_screenshot
    import cv2

    while True:
        current_pos = minimap.get_character_positions("self")
        print(current_pos)
        # img = take_screenshot(HANDLE)
        # cv2.imshow("test", img)
        # test = cv2.Canny(img, 0, 300, L2gradient=True)
        # cv2.imshow("test2", test)
        # cv2.waitKey(1)
