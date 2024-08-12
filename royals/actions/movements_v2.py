from typing import Literal
from botting import controller

FIRST_DELAY = 0.5


def _create_initial_input(
    handle: int,
    direction: str,
    secondary_direction: str | None,
) -> controller.KeyboardInputWrapper:
    """
    Creates a FocusedInput structure to initiate a series of movements.
    Looks into currently held movement keys that may have been sent from previous
    instances and ensures that they are released.
    :param handle: The handle of the window to send the input to.
    :param direction: The primary direction of the movement.
    :param secondary_direction: The secondary direction of the movement.
    :return: The FocusedInput structure that will simultaneously release all movement
    keys aside from direction and secondary_direction.
    """
    held_keys = controller.get_held_movement_keys(handle)
    _initial_structure = controller.KeyboardInputWrapper(handle)
    if direction in held_keys:
        held_keys.remove(direction)
    if secondary_direction in held_keys:
        held_keys.remove(secondary_direction)
    if held_keys:
        _initial_structure.append(
            held_keys, ["keyup"] * len(held_keys), next(controller.random_delay)  # noqa
        )
    return _initial_structure


def move(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    secondary_direction: Literal["up", "down"] = None,
    *,
    duration: float,
    structure: controller.KeyboardInputWrapper = None
) -> controller.KeyboardInputWrapper:
    """
    Creates the input structures and delays to describe the movement.
    If the movement extends on a previous input, the input structures and delays are
    appended onto the FocusedInput instance.
    :param handle:
    :param direction:
    :param secondary_direction:
    :param duration:
    :param structure:
    :return:
    """
    initial_duration = getattr(structure, "duration", 0)
    limit = initial_duration + duration
    if structure is None:
        structure = _create_initial_input(handle, direction, secondary_direction)

    repeated_key: str = secondary_direction or direction  # noqa

    first_keys = [direction]
    if secondary_direction:
        first_keys.append(secondary_direction)
    for key in structure.keys_held:
        if key in [direction, secondary_direction]:
            continue
        structure.append(key, "keyup", next(controller.random_delay))

    first_delay = (
        FIRST_DELAY
        if repeated_key not in structure.keys_held
        else next(controller.random_delay)
    )
    structure.append(first_keys, ["keydown"] * len(first_keys), first_delay)  # noqa
    structure.fill(repeated_key, "keydown", controller.random_delay, limit=limit)
    return structure
