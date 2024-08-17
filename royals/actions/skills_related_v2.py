from botting import controller
from botting.models_abstractions import Skill


def cast_skill(
    handle: int,
    ign: str,
    skill: Skill,
    direction: str = None,
) -> controller.KeyboardInputWrapper:
    """
    Casts a skill with the automated repeat feature (focused).
    :param handle:
    :param ign:
    :param skill:
    :param direction:
    :return:
    """
    structure = controller.KeyboardInputWrapper(handle)
    if direction:
        held_keys = controller.get_held_movement_keys(handle)
        if direction in held_keys:
            held_keys.remove(direction)
        if held_keys:
            structure.append(
                held_keys, ["keyup"] * len(held_keys), next(controller.random_delay)  # noqa
            )
        structure.append(direction, 'keydown', 2 * next(controller.random_delay))
        structure.append(direction, 'keyup', next(controller.random_delay))

    structure.fill(
        skill.key_bind(ign), 'keydown', controller.random_delay, skill.animation_time
    )
    structure.forced_key_releases.append(skill.key_bind(ign))
    return structure



def cast_skill_single_press():
    pass


def cast_skill_silenced():
    pass
