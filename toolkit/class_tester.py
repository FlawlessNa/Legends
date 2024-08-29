import asyncio
import win32gui
from botting import controller
from botting.utilities import client_handler, Box
from royals import royals_ign_finder

from royals.model.minimaps import KampungVillageMinimap, FantasyThemePark1Minimap

from royals.model.characters import Bishop
from royals.model.mechanics.movement_mechanics import Movements
from royals.actions.skills_related_v2 import cast_skill
from royals.actions.movements_v2 import telecast

HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)


if __name__ == "__main__":
    left, top, right, bottom = win32gui.GetClientRect(HANDLE)
    region = Box(left=right - 150, top=top + 45, right=right, bottom=85)
    bishop = Bishop("WrongDoor", "Elephant Cape", "large")
    origin, target = (8, 22), (43, 22)
    minimap = FantasyThemePark1Minimap()
    minimap.generate_grid_template(allow_teleport=True)
    move_handler = Movements("WrongDoor", HANDLE, bishop.skills["Teleport"], minimap)
    area_box = minimap.get_map_area_box(HANDLE)
    path = move_handler.compute_path(origin, target)
    moves = move_handler.path_into_movements(path)
    action = move_handler.movements_into_action(moves, 1.0)
    print("Action", action.duration)
    cast = cast_skill(HANDLE, "WrongDoor", bishop.skills["Genesis"])
    print("Cast Skill", cast)
    # asyncio.run(cast.send())
    telecast = telecast(action, "WrongDoor", "c", bishop.skills["Genesis"])
    # print('Telecast', telecast.duration)
    asyncio.run(telecast.send())
    # asyncio.run(action.send())
