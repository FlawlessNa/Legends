import cv2
import keyboard

import royals.model.minimaps as minimaps
from royals.model.mechanics.movement_mechanics import Movements
from royals.model.characters import Bishop

MINIMAP = minimaps.PathOfTime1Minimap()
TELEPORT = True

# Insert nodes that lead to "difficult" transitions in-game.
# The goal is simply to be able to inspect the path, the movements & the action.
# Then, you can fine-tune the Movements parsing to improve this.
START_POS = [(x, 54) for x in range(6, 20)]
TARGET_POS = [(x, 39) for x in range(15, 20)]

# TODO -> Add "navigation" of starting point + end points on the canvas with automatic
# Recalculation of path, moves,  & action.
# Plus, add hotkeys to print movements/action/path.


def exit():
    raise SystemExit


keyboard.add_hotkey("escape", exit)


if __name__ == "__main__":
    MINIMAP.generate_grid_template(TELEPORT, 1.15, 1.02)
    skill = Bishop.skills["Teleport"] if TELEPORT else None
    moves = Movements("StarBase", 0, skill, MINIMAP)
    for start in START_POS:
        for end in TARGET_POS:
            path = moves.compute_path(start, end)
            movements = moves.path_into_movements(path)
            structure = moves.movements_into_action(movements)
            keyboard.wait("space")
