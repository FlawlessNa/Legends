from timeit import timeit

from royals.game_interface.dynamic_components.minimap import Minimap

test = Minimap(0x00620DFE)

FUNC = test.get_character_positions
N_TIMES = 100
total_time = timeit(FUNC, number=N_TIMES)
print(
    f"Average time for {N_TIMES} runs: {total_time / N_TIMES} seconds for function {FUNC.__name__}"
)
