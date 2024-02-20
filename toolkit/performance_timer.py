from functools import partial
from timeit import timeit
from botting.utilities import client_handler
from royals import royals_ign_finder

from royals.models_implementations.minimaps import LudiFreeMarketTemplateMinimap
from royals.models_implementations.mechanics.path_into_movements import get_to_target
from royals.characters import Bishop

test = LudiFreeMarketTemplateMinimap()
test.generate_grid_template(True)
HANDLE = client_handler.get_client_handle("WrongDoor", royals_ign_finder)
map_area = test.get_map_area_box(HANDLE)
current_pos = test.get_character_positions(HANDLE, map_area_box=map_area).pop()
bishop = Bishop("WrongDoor", "Elephant Cape", "large")

FUNC = partial(
    get_to_target,
    current_pos,
    (0, 0),
    test,
    HANDLE,
    "alt",
    bishop.skills["Teleport"],
    "WrongDoor",
)
N_TIMES = 100
total_time = timeit(FUNC, number=N_TIMES)
print(
    f"Average time for {N_TIMES} runs: {total_time / N_TIMES} seconds for function {FUNC}"
)
