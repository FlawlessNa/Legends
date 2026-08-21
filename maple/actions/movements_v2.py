import random
from typing import Literal
from botting import controller
from botting.models_abstractions import Skill

from .skills_related_v2 import cast_skill

FIRST_DELAY = 0.5


def _resolve_held_keys(
    structure: controller.KeyboardInputWrapper | None,
    handle: int,
    initial_held_keys: frozenset[str] | None,
) -> set[str]:
    """
    Determines the movement keys held before this builder call starts.
    Chains onto `structure` when one exists (no live query needed); otherwise defers to
    `initial_held_keys` when supplied, and only falls back to the live Win32 query when
    neither is available - so a caller providing either keeps compilation deterministic.
    """
    if structure is not None:
        return structure.keys_held
    if initial_held_keys is not None:
        return set(initial_held_keys)
    return set(controller.get_held_movement_keys(handle))

#
# def _create_initial_input(
#     handle: int,
#     direction: str,
#     secondary_direction: str | None,
# ) -> controller.KeyboardInputWrapper:
#     """
#     Creates a FocusedInput structure to initiate a series of movements.
#     Looks into currently held movement keys that may have been sent from previous
#     instances and ensures that they are released.
#     :param handle: The handle of the window to send the input to.
#     :param direction: The primary direction of the movement.
#     :param secondary_direction: The secondary direction of the movement.
#     :return: The FocusedInput structure that will simultaneously release all movement
#     keys aside from direction and secondary_direction.
#     """
#     held_keys = controller.get_held_movement_keys(handle)
#     _initial_structure = controller.KeyboardInputWrapper(handle)
#     if direction in held_keys:
#         held_keys.remove(direction)
#     if secondary_direction in held_keys:
#         held_keys.remove(secondary_direction)
#
#     # ALWAYS release opposite key on directional movement - should prevent being stuck
#     # but also causes unnecessary key releases
#     if direction == 'right' and 'left' not in held_keys:
#         held_keys.append('left')
#     elif direction == 'left' and 'right' not in held_keys:
#         held_keys.append('right')
#     if held_keys:
#         _initial_structure.append(
#             held_keys, ["keyup"] * len(held_keys), next(controller.random_delay)  # noqa
#         )
#     return _initial_structure


def move(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    secondary_direction: Literal["up", "down"] = None,
    *,
    duration: float,
    structure: controller.KeyboardInputWrapper = None,
    release_keys: str | list[str] = None,
    initial_held_keys: frozenset[str] | None = None,
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
    :param release_keys: If specified, release events are inserted before the movement,
        provided the release_keys are held.
    :param initial_held_keys: Held movement keys to assume when `structure` is None,
        instead of querying the live Win32 state. Enables deterministic offline
        compilation of a movement plan's first builder call.
    :return:
    """
    initial_duration = getattr(structure, "duration", 0)
    keys_held = _resolve_held_keys(structure, handle, initial_held_keys)
    repeated_key: str = secondary_direction or direction  # noqa
    limit = initial_duration + duration
    if isinstance(release_keys, str):
        release_keys = [release_keys]


    first_keys = [direction]
    if secondary_direction:
        first_keys.append(secondary_direction)
    first_delay = (
        # TODO - see if "not in keys_held + ["up"]" is necessary and if so, document why
        # if repeated_key not in list(structure.keys_held) + ["up"]
        min(FIRST_DELAY, duration) if repeated_key not in keys_held else next(controller.random_delay)
    )
    if structure is None:
        release_index = 0
        structure = controller.KeyboardInputWrapper(
            handle, first_keys, ["keydown"] * len(first_keys) , [first_delay], # noqa
            initial_held_keys=initial_held_keys,
        )
    else:
        release_index = len(structure.keys)
        if not all(key in keys_held for key in first_keys):
            structure.append(
                first_keys, ["keydown"] * len(first_keys), first_delay  # noqa
            )

    if release_keys:
        actual_releases = list(set(release_keys).intersection(keys_held))
        if actual_releases:
            structure.insert(
                release_index,
                actual_releases,
                ["keyup"] * len(actual_releases),
                next(controller.random_delay),
            )
    structure.fill(repeated_key, "keydown", controller.random_delay, limit=limit)
    return structure


def single_jump(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    jump_key: str,
    structure: controller.KeyboardInputWrapper = None,
    repeat_key: str = None,
    initial_held_keys: frozenset[str] | None = None,
) -> controller.KeyboardInputWrapper:
    # TODO - Adjust the hard-coded 0.75 delay appropriately
    keys_held = _resolve_held_keys(structure, handle, initial_held_keys)
    first_keys = [direction, jump_key] if direction not in keys_held else [jump_key]
    if structure is None:
        structure = controller.KeyboardInputWrapper(
            handle,
            first_keys,
            ["keydown"] * len(first_keys),  # noqa
            [next(controller.random_delay) * 2] * len(first_keys),
            initial_held_keys=initial_held_keys,
        )
    else:
        for key in first_keys:
            structure.append(
                key,
                "keydown",  # noqa
                next(controller.random_delay)
            )
    if repeat_key is not None:
        structure.fill(
            repeat_key,
            "keydown",
            controller.random_delay,
            limit=0.75 + structure.duration
        )
    structure.append(jump_key, "keyup", 0.75)
    #
    # elif direction == "down":
    #     # Special case where we voluntarily trigger the automatic repeat feature
    #     # to avoid static position.
    #     initial_duration = structure.duration
    #     structure.append(direction, "keydown", next(controller.random_delay) * 2)
    #     structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
    #     structure.append(jump_key, "keyup", next(controller.random_delay) * 2)
    #     while structure.duration - initial_duration < 0.75:
    #         structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
    #         structure.append(jump_key, "keyup", next(controller.random_delay) * 2)
    # else:
    #     structure.append(direction, "keydown", next(controller.random_delay) * 2)
    #     structure.append(jump_key, "keydown", next(controller.random_delay) * 2)
    #     structure.append(jump_key, "keyup", 0.75)

    # structure.forced_key_releases.append(jump_key)
    return structure


def jump_on_rope(
    handle: int,
    direction: Literal["left", "right"],
    jump_key: str,
    structure: controller.KeyboardInputWrapper = None,
    initial_held_keys: frozenset[str] | None = None,
) -> controller.KeyboardInputWrapper:
    """
    Jump on a rope. The secondary direction is maintained after the jump.
    :param handle:
    :param direction:
    :param jump_key:
    :param structure:
    :param initial_held_keys: Held movement keys to assume when `structure` is None,
        instead of querying the live Win32 state.
    :return:
    """
    if structure is None:
        structure = controller.KeyboardInputWrapper(
            handle, [direction], ["keydown"], [next(controller.random_delay)],  # noqa
            initial_held_keys=initial_held_keys,
        )

    for key in structure.keys_held:
        if key == direction:
            continue
        # Longer delay to try preventing "static" jumps
        structure.append(key, "keyup", next(controller.random_delay) * 5)

    if direction in structure.keys_held:
        structure.append([jump_key, "up"], ["keydown", "keydown"], 0.75)
        structure.append(
            [jump_key, direction], ["keyup", "keyup"], next(controller.random_delay) * 2
        )

    else:
        structure.append(direction, "keydown", next(controller.random_delay) * 5)
        structure.append([jump_key, "up"], ["keydown", "keydown"], 0.75)
        structure.append(
            [jump_key, direction], ["keyup", "keyup"], next(controller.random_delay) * 2
        )

    structure.forced_key_releases.append(jump_key)
    return structure


def teleport(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    num_times: int = 1,
    structure: controller.KeyboardInputWrapper = None,
    repeat_key: str = None,
    initial_held_keys: frozenset[str] | None = None,
) -> controller.KeyboardInputWrapper:
    """
    Casts teleport in a given direction.
    :param handle:
    :param ign:
    :param teleport_skill:
    :param direction:
    :param num_times:
    :param structure:
    :param repeat_key:
    :param initial_held_keys: Held movement keys to assume when `structure` is None,
        instead of querying the live Win32 state.
    :return:
    """
    initial_duration = getattr(structure, 'duration', 0)
    keys_held = _resolve_held_keys(structure, handle, initial_held_keys)
    limit = initial_duration + teleport_skill.animation_time * num_times
    if structure is None:
        structure = controller.KeyboardInputWrapper(
            handle, [direction], ["keydown"], [next(controller.random_delay)],  # noqa
            initial_held_keys=initial_held_keys,
        )
    # if structure is None:
    #     structure = _create_initial_input(handle, direction, None)

    # for key in structure.keys_held:
    #     if key == direction:
    #         continue
    #     elif key == "up" and direction in ["left", "right"]:
    #         # TODO - Hardcodings to improve/remove
    #         structure.append(key, "keyup", 0.1)
    #     else:
    #         structure.append(key, "keyup", next(controller.random_delay))

    if direction not in keys_held:
        structure.append(direction, "keydown", next(controller.random_delay))
    if repeat_key is None:
        structure.fill(
            teleport_skill.key_bind(ign),
            "keydown",
            controller.random_delay,
            limit=limit,
        )
    else:
        structure.append(
            teleport_skill.key_bind(ign), "keydown", next(controller.random_delay)
        )
        structure.append(
            teleport_skill.key_bind(ign), "keyup", next(controller.random_delay)
        )
        structure.fill(repeat_key, "keydown", controller.random_delay, limit=limit)
    if direction == "down" and direction not in structure.forced_key_releases:
        structure.forced_key_releases.append(direction)
    if teleport_skill.key_bind(ign) not in structure.forced_key_releases:
        structure.forced_key_releases.append(teleport_skill.key_bind(ign))
    return structure

#
# def telecast(
#     structure: controller.KeyboardInputWrapper,
#     ign: str,
#     teleport_key: str,
#     ultimate_skill: Skill,
# ) -> controller.KeyboardInputWrapper:
#     """
#     This function does not extend the structure like other functions in this module.
#     Instead, it introspects that structure and adds ultimate cast keystrokes in
#     combination to the teleport keystrokes.
#     :param structure:
#     :param ign:
#     :param teleport_key:
#     :param ultimate_skill:
#     :return:
#     """
#     if teleport_key not in structure.keys:
#         print("No telecast possible. Casting ultimate instead")
#         return cast_skill(structure.handle, ign, ultimate_skill)
#
#     # Modify the structure such that teleports are combined with ultimate casts
#     ultimate_key = ultimate_skill.key_bind(ign)
#     structure.forced_key_releases.append(ultimate_key)
#     for idx, (key, event) in enumerate(zip(structure.keys, structure.events)):
#         if key == teleport_key and event == "keydown":
#             structure.keys[idx] = [teleport_key, ultimate_key]
#             structure.events[idx] = ["keydown", "keydown"]
#     return structure.truncate(ultimate_skill.animation_time)


def random_jump(handle: int, jump_key: str) -> controller.KeyboardInputWrapper:
    direction = random.choice(["left", "right"])
    controller.release_all(handle)
    structure = single_jump(handle, direction, jump_key)
    structure.forced_key_releases.append(direction)
    return structure
