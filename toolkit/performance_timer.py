from functools import partial
from timeit import timeit

from royals.models_implementations.minimaps import LudiFreeMarketTemplate

test = LudiFreeMarketTemplate()
HANDLE = 0x002E05E6
map_area = test.get_map_area_box(HANDLE)
FUNC = partial(test.get_character_positions, HANDLE, "Stranger", map_area_box=map_area)
N_TIMES = 100
total_time = timeit(FUNC, number=N_TIMES)
print(
    f"Average time for {N_TIMES} runs: {total_time / N_TIMES} seconds for function {FUNC}"
)
