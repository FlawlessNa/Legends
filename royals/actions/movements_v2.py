from typing import Literal
from botting import controller
from botting.models_abstractions import Skill

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
        if repeated_key not in list(structure.keys_held) + ['up']
        else next(controller.random_delay)
    )
    structure.append(first_keys, ["keydown"] * len(first_keys), first_delay)  # noqa
    structure.fill(repeated_key, "keydown", controller.random_delay, limit=limit)
    return structure


def single_jump(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    jump_key: str,
    structure: controller.KeyboardInputWrapper = None
) -> controller.KeyboardInputWrapper:
    # TODO - Adjust the hard-coded 0.75 delay appropriately
    if structure is None:
        structure = _create_initial_input(handle, direction, None)
    for key in structure.keys_held:
        if key == direction:
            continue
        structure.append(key, "keyup", next(controller.random_delay))

    if direction in ["left", "right"]:
        if direction in structure.keys_held:
            structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
            structure.append(jump_key, "keyup", 0.75)
        else:
            structure.append(direction, "keydown", next(controller.random_delay) * 2)
            structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
            structure.append(jump_key, "keyup", 0.75)
    elif direction == "down":
        # Special case where we voluntarily trigger the automatic repeat feature
        # to avoid static position.
        initial_duration = structure.duration
        structure.append(direction, "keydown", next(controller.random_delay) * 2)
        structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
        structure.append(jump_key, "keyup", next(controller.random_delay) * 2)
        while structure.duration - initial_duration < 0.75:
            structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
            structure.append(jump_key, "keyup", next(controller.random_delay) * 2)
    else:
        structure.append(direction, "keydown", next(controller.random_delay) * 2)
        structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
        structure.append(jump_key, "keyup", 0.75)

    return structure


def jump_on_rope(
    handle: int,
    direction: Literal["left", "right"],
    jump_key: str,
    structure: controller.KeyboardInputWrapper = None
) -> controller.KeyboardInputWrapper:
    """
    Jump on a rope. The secondary direction is maintained after the jump.
    :param handle:
    :param direction:
    :param jump_key:
    :param structure:
    :return:
    """
    if structure is None:
        structure = _create_initial_input(handle, direction, None)
    for key in structure.keys_held:
        if key == direction:
            continue
        structure.append(key, "keyup", next(controller.random_delay))

    if direction in structure.keys_held:
        structure.append(
            [jump_key, "up"], ["keydown", "keydown"], 0.75
        )
        structure.append(
            [jump_key, direction], ["keyup", "keyup"], next(controller.random_delay) * 2
        )

    else:
        structure.append(
            direction, "keydown", next(controller.random_delay) * 2
        )
        structure.append(
            [jump_key, "up"], ["keydown", "keydown"], 0.75
        )
        structure.append(
            [jump_key, direction], ["keyup", "keyup"], next(controller.random_delay) * 2
        )

    return structure


def teleport(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    num_times: int = 1,
    structure: controller.KeyboardInputWrapper = None
) -> controller.KeyboardInputWrapper:
    """
    Casts teleport in a given direction.
    :param handle:
    :param ign:
    :param teleport_skill:
    :param direction:
    :param num_times:
    :param structure:
    :return:
    """
    if structure is None:
        structure = _create_initial_input(handle, direction, None)

    initial_duration = structure.duration
    limit = initial_duration + teleport_skill.animation_time * num_times
    for key in structure.keys_held:
        if key == direction:
            continue
        elif key == 'up' and direction in ["left", "right"]:
            # TODO - Hardcodings to improve/remove
            structure.append(key, "keyup", 0.1)
        else:
            structure.append(key, "keyup", next(controller.random_delay))

    if direction not in structure.keys_held:
        structure.append(direction, "keydown", next(controller.random_delay))
    structure.fill(
        teleport_skill.key_bind(ign),
        "keydown",
        controller.random_delay,
        limit=limit
    )
    enforce_last_inputs = [teleport_skill.key_bind(ign)]
    if direction == "down":
        enforce_last_inputs.append(direction)
    structure.forced_key_releases = enforce_last_inputs
    return structure
