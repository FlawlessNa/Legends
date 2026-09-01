import asyncio

from botting import controller
from botting.models_abstractions import Skill

# The most a single filled Step can cost: `random_delay` yields at most `1.05 * DELAY`,
# and every Step also pays the send loop's `OVERHEAD`. Reserving this much of the cast
# window guarantees the closing keyup is *sent* strictly inside it - `fill` stops on the
# first duration at or past its limit, so without the reservation the keyup lands at or
# after the animation completes and the game auto-repeats a second cast (issue #98).
_MAX_STEP_COST: float = 1.05 * controller.DELAY + controller.OVERHEAD


def cast_skill(
    handle: int,
    ign: str,
    skill: Skill,
    direction: str | None = None,
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
            ups: list[controller.EVENTS] = ["keyup"] * len(held_keys)
            structure.append(
                held_keys,
                ups,
                next(controller.random_delay),
            )
        structure.append(direction, "keydown", 2 * next(controller.random_delay))
        structure.append(direction, "keyup", next(controller.random_delay))

    # The cast window opens where the fill does, not where the sequence does. `fill`'s
    # limit is an *absolute* sequence duration, so passing `animation_time` raw spent
    # the direction Steps above out of the cast's own budget - every other `fill` call
    # site passes a delta (`teleport`: `initial_duration + animation_time * num_times`).
    fill_start = structure.duration
    deadline = fill_start + skill.animation_time
    structure.fill(
        skill.key_bind(ign),
        "keydown",
        controller.random_delay,
        limit=deadline - _MAX_STEP_COST,
    )
    if skill.key_bind(ign) not in structure.keys_held:
        # `animation_time` too short to fit a filled Step. Press once anyway: a
        # `cast_skill` that compiles to no skill Step has silently not cast the skill.
        structure.append(skill.key_bind(ign), "keydown", next(controller.random_delay))
    # Close the skill key's Hold inside the sequence instead of leaving it to the
    # forced volley. Unguarded now: the branch above makes the keydown unconditional,
    # so this can no longer be a phantom release of a key never pressed (**A6**).
    structure.append(skill.key_bind(ign), "keyup", next(controller.random_delay))
    structure.forced_key_releases.append(skill.key_bind(ign))
    return structure


def cast_skill_compiler(
    initial_held_keys: frozenset[str] | None,
    *,
    handle: int,
    ign: str,
    skill: Skill,
    direction: str | None = None,
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


def cast_skill_silenced() -> None:
    pass
