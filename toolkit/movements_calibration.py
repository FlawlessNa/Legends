import asyncio
import cv2
import numpy as np
import keyboard
import royals.model.minimaps as minimaps
from royals.model.mechanics.movement_mechanics import Movements
from royals.model.characters import Bishop

# TODO - Improve this script. It's a bit messy.
# TODO - Investigate why "RIGHT_JUMP_AND_UP" are jumping from two horizontal nodes, while it's three for the other direction
# -> it looks like its the trajectory algorithm that does this. Finish investigating.
# Use multiprocessing?
# Add two modes: one uses character in-game position, other one uses keyboard module
# Add ability to toggle on/off for:
# left trajectory (with fall only option?) + node that connects, if any
# right trajectory (with fall only option?) + node that connects, if any
# teleport range (draw a cross (or just the end-points) around character) + node that connects, if any
MINIMAP = minimaps.PathOfTime1Minimap()
TELEPORT = True
MINIMAP.generate_grid_template(TELEPORT, 1.15, 1.02)
skill = Bishop.skills["Teleport"] if TELEPORT else None
moves = Movements("StarBase", 0, skill, MINIMAP)
Movements._debug = False

# Insert nodes that lead to "difficult" transitions in-game.
# The goal is simply to be able to inspect the path, the movements & the action.
# Then, you can fine-tune the Movements parsing to improve this.
START_POS = [20, 38]
TARGET_POS = [20, 24]


def refresh_all(start: list[int], end: list[int]):
    beg = tuple(start)
    finish = tuple(end)
    print(beg, finish)
    path = moves.compute_path(beg, finish)
    canvas = np.zeros(
        (moves.minimap.map_area_height, moves.minimap.map_area_width),
        dtype=np.uint8,
    )
    canvas = moves.minimap._preprocess_img(canvas)
    path_img = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    cv2.drawMarker(
        path_img, (start[0], start[1]), (0, 0, 255), cv2.MARKER_CROSS, markerSize=3
    )
    cv2.drawMarker(
        path_img, (end[0], end[1]), (255, 0, 0), cv2.MARKER_CROSS, markerSize=3
    )
    for node in path:
        path_img[node.y, node.x] = (0, 255, 0)
    path_img = cv2.resize(path_img, None, fx=5, fy=5)
    cv2.imshow(f"_DEBUG_ Mode - PathFinding {moves.ign}", path_img)
    cv2.waitKey(1)
    movements = moves.path_into_movements(path)
    print(movements)
    structure = moves.movements_into_action(movements)


def update_start_pos(dx, dy):
    START_POS[0] += dx
    START_POS[1] += dy
    refresh_all(START_POS, TARGET_POS)


def update_target_pos(dx, dy):
    TARGET_POS[0] += dx
    TARGET_POS[1] += dy
    refresh_all(START_POS, TARGET_POS)


async def main():
    refresh_all(START_POS, TARGET_POS)
    while True:
        if keyboard.is_pressed('esc'):
            break
        if keyboard.is_pressed('ctrl+shift+right'):
            update_target_pos(2, 0)
        elif keyboard.is_pressed('ctrl+right'):
            update_target_pos(1, 0)
        elif keyboard.is_pressed('shift+right'):
            update_start_pos(2, 0)
        elif keyboard.is_pressed('right'):
            update_start_pos(1, 0)

        elif keyboard.is_pressed('ctrl+shift+left'):
            update_target_pos(-2, 0)
        elif keyboard.is_pressed('ctrl+left'):
            update_target_pos(-1, 0)
        elif keyboard.is_pressed('shift+left'):
            update_start_pos(-2, 0)
        elif keyboard.is_pressed('left'):
            update_start_pos(-1, 0)

        elif keyboard.is_pressed('ctrl+shift+up'):
            update_target_pos(0, -2)
        elif keyboard.is_pressed('ctrl+up'):
            update_target_pos(0, -1)
        elif keyboard.is_pressed('shift+up'):
            update_start_pos(0, -2)
        elif keyboard.is_pressed('up'):
            update_start_pos(0, -1)

        elif keyboard.is_pressed('ctrl+shift+down'):
            update_target_pos(0, 2)
        elif keyboard.is_pressed('ctrl+down'):
            update_target_pos(0, 1)
        elif keyboard.is_pressed('shift+down'):
            update_start_pos(0, 2)
        elif keyboard.is_pressed('down'):
            update_start_pos(0, 1)
        await asyncio.sleep(0.1)


if __name__ == "__main__":
    asyncio.run(main())
