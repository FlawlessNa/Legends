import asyncio
from botting import controller
from botting.models_abstractions import Skill


def cast_skill(
    handle: int,
    ign: str,
    skill: Skill,
    direction: str = None,
    initial_held_keys: frozenset[str] | None = None,
) -> controller.KeyboardInputWrapper:
    """
    Casts a skill with the automated repeat feature (focused).
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :param initial_held_keys: Movement keys held before the cast, instead of querying
        the live state. Only Main Process owns a Held-Keys Ledger to query, so any
        caller compiling elsewhere must supply this - see `cast_skill_compiler`.
    :return:
    """
    structure = controller.KeyboardInputWrapper(
        handle, initial_held_keys=initial_held_keys
    )
    if initial_held_keys is None:
        held_keys = controller.get_held_movement_keys(handle)
    else:
        held_keys = [k for k in controller.OPPOSITES if k in initial_held_keys]

    if "down" in held_keys:
        held_keys.remove("down")
        # Larger delay to prevent skill from being cast while crouched
        structure.append("down", "keyup", 0.1)

    if direction:
        if direction in held_keys:
            held_keys.remove(direction)
        if held_keys:
            structure.append(
                held_keys,
                ["keyup"] * len(held_keys),
                next(controller.random_delay),  # noqa
            )
        structure.append(direction, "keydown", 2 * next(controller.random_delay))
        structure.append(direction, "keyup", next(controller.random_delay))

    structure.fill(
        skill.key_bind(ign), "keydown", controller.random_delay, skill.animation_time
    )
    structure.forced_key_releases.append(skill.key_bind(ign))
    return structure


def cast_skill_compiler(
    initial_held_keys: frozenset[str] | None,
    *,
    handle: int,
    ign: str,
    skill: Skill,
    direction: str = None,
) -> controller.KeyboardInputWrapper:
    """
    `cast_skill` in the shape `controller.compile_and_send` expects: held keys first
    and positional, everything else frozen into a partial when the ActionRequest is
    composed. Lets a skill cast be compiled at dispatch, against the ledger, the same
    way a movement is.
    """
    return cast_skill(
        handle, ign, skill, direction, initial_held_keys=initial_held_keys
    )


async def cast_skill_single_press(handle: int, ign: str, skill: Skill) -> None:
    await controller.press(handle, skill.key_bind(ign))
    await asyncio.sleep(skill.animation_time)


def cast_skill_silenced():
    pass
