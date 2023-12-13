import cv2
from botting.utilities import client_handler, take_screenshot
from royals.interface.fixed_components.character_stats import CharacterStats

HANDLE = 0x02300A26

if __name__ == "__main__":
    stats = CharacterStats()
    img = take_screenshot(HANDLE, stats.ign_box)
    cv2.imshow('test', img)
    cv2.waitKey(1)
    print(client_handler.get_open_clients())
    print(stats.get_ign(HANDLE))
    print(client_handler.get_client_handle('FarmFest1', stats.get_ign))