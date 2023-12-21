import time
import math

from royals.models_implementations.minimaps import PathOfTime1

# Once the script starts, it continuously monitors the character's position on the minimap.
# As soon as the character starts moving, the script logs the character's position with a timestamp.
# As soon as the character reaches the target position, the script saves the data and stops.

TARGET = (50, 54)  # Target position on the minimap
HANDLE = 0x02300A26  # Handle to the game window
minimap = PathOfTime1()  # Minimap implementation in which the speed is tested (Assumption is that speed may vary from map to map)

initial_pos = minimap.get_character_positions(HANDLE).pop()  # Initial position of the character
map_area = minimap.get_map_area_box(HANDLE)  # Map area box
stamps = []
positions = []
while True:

    current_pos = minimap.get_character_positions(HANDLE, map_area_box=map_area).pop()
    # Start recording data along with precise timestamps
    positions.append(current_pos)
    stamps.append(time.perf_counter())
    if current_pos == initial_pos:
        continue
    elif current_pos == TARGET:
        break

print(f"Character moved from {initial_pos} to {TARGET} in {stamps[-1] - stamps[0]} seconds.")
print(f"Average speed: {math.dist(initial_pos, TARGET) / (stamps[-1] - stamps[0])} nodes per second.")