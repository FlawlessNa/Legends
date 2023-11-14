from royals.game_interface.fixed_components.in_game_chat.chat_feed import ChatFeed
from royals.game_interface.dynamic_components.minimap import Minimap
from royals.game_model.maps.kerning_line1_area1 import KerningLine1Area1
HANDLE = 0x00620DFE
test = Minimap(HANDLE)
# test = ChatFeed(HANDLE)
from royals.utilities import take_screenshot
import cv2

mapp = KerningLine1Area1()
while True:
    current_pos = test.get_character_positions().pop()
    print(mapp.get_current_feature(current_pos))
