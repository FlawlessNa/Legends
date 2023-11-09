"""
Helper script to continuously record minimap positioning and record platform endpoints, portals, ladders, etc. based on key presses.
"""
from royals.game_interface.dynamic_components.minimap import Minimap

if __name__ == "__main__":
    HANDLE = 0x00040E52
    minimap = Minimap(HANDLE)
    while True:
        minimap.get_character_positions("self")
