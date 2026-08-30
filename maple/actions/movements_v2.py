import logging
import random
from typing import Callable, Literal
from botting import PARENT_LOG, controller, emit_event
from botting.models_abstractions import Skill
from maple.telemetry_events import (
    COMBAT_TELECAST_UNAVAILABLE,
    TelecastUnavailablePayload,
)

from .skills_related_v2 import cast_skill

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

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
        if repeat_key not in structure.forced_key_releases:
            structure.forced_key_releases.append(repeat_key)
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

    structure.forced_key_releases.append(jump_key)
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


def _has_keydown(structure: controller.KeyboardInputWrapper, key: str) -> bool:
    """
    Whether any Step of `structure` presses `key` down. A Step carries either a single
    key or a list of simultaneous ones, so both shapes are walked.
    """
    for step_keys, step_events in zip(structure.keys, structure.events):
        if isinstance(step_keys, list):
            if any(
                k == key and e == "keydown" for k, e in zip(step_keys, step_events)
            ):
                return True
        elif step_keys == key and step_events == "keydown":
            return True
    return False


def _teleport_regions(
    structure: controller.KeyboardInputWrapper, teleport_key: str
) -> dict[int, int]:
    """
    The teleport regions of a compiled Input Sequence, as `{start: stop}` half-open
    Step index ranges - each a maximal run of consecutive Steps carrying
    `teleport_key` on its own.

    A run absorbs an explicit keyup sitting against the keydowns (the shape `teleport`
    builds when handed a `repeat_key`), so a rebuild that presses and releases the key
    itself leaves no phantom release behind it. A run holding no keydown is not a
    region: nothing there was ever pressed to fuse a cast into.
    """
    runs = []
    start = None
    for idx, key in enumerate(structure.keys):
        if key == teleport_key:
            if start is None:
                start = idx
        elif start is not None:
            runs.append((start, idx))
            start = None
    if start is not None:
        runs.append((start, len(structure.keys)))
    return {
        start: stop
        for start, stop in runs
        if "keydown" in structure.events[start:stop]
    }


def _append_telecast_taps(
    structure: controller.KeyboardInputWrapper,
    teleport_key: str,
    ultimate_key: str,
    budget: float,
    cadence: float,
) -> None:
    """
    Appends paired presses of the teleport and ultimate keys, one per `cadence`, for
    as long as `budget` lasts.

    A tap is a down of both keys together, an up of both together, and then a wait for
    the teleport animation - carried as the delay on the keyup Step, so the gap is a
    single Step rather than a fill. That is the whole point of the rebuild: a key that
    stays down does not resume auto-repeating once another press has happened, so
    filling the gap would fabricate a repeat run the game never produces from a human.
    The direction key stays down across the gap; only its repeating is gone.

    At least one tap is always emitted, and the last one is shortened to whatever
    budget is left rather than overrunning the region.
    """
    remaining = budget
    while True:
        press = next(controller.random_delay)
        gap = min(cadence, remaining) - press - 2 * controller.OVERHEAD
        if gap <= 0:
            # Cadence shorter than a single down/up: no room to wait, tap and move on.
            gap = next(controller.random_delay)
        structure.append([teleport_key, ultimate_key], ["keydown", "keydown"], press)
        structure.append([teleport_key, ultimate_key], ["keyup", "keyup"], gap)
        remaining -= press + gap + 2 * controller.OVERHEAD
        if remaining < controller.DELAY:
            # Too little left to hold another press - and below the float noise the
            # subtraction above leaves behind.
            return


def telecast(
    structure: controller.KeyboardInputWrapper,
    ign: str,
    teleport_skill: Skill,
    ultimate_skill: Skill,
) -> controller.KeyboardInputWrapper:
    """
    Fuses an ultimate cast into an already-compiled Input Sequence.

    Unlike the builders above, this does not extend a structure: it walks a finished
    one and **rebuilds its teleport regions**, so the character casts while it blinks.
    Every other Step is copied through untouched. The result is truncated to the
    ultimate's animation time - past that the cast is over, and the rest of the
    movement belongs to whatever the bot decides next.

    This used to rewrite each teleport keydown in place into a simultaneous
    `[teleport_key, ultimate_key]` Step. Those keydowns are a `fill` at the input
    cadence, which is faithful for a *held* teleport key but not for a fused pair:
    nothing a human does presses a second key thirty times a second. Spy++ settles
    what is really being imitated - only the last key pressed auto-repeats, and
    auto-repeat never comes back to a key still held once another press has happened -
    so telecasting is re-pressing both keys together to keep teleporting while the
    ultimate casts. The cadence is the teleport's own `animation_time`, which also
    keeps the plan's distance intent: `teleport` budgets `animation_time * num_times`,
    so one press per cadence yields exactly `num_times` teleports.

    The ultimate key is declared for forced release. Each tap now closes its Hold
    inside the sequence, so **A2 Terminal Release** and **D1 Cancel Safety** no longer
    rest on that declaration alone - but a truncation landing between a tap's down and
    its up still does, and the forced volley only fires for keys the Held-Keys Ledger
    reports down, so declaring it stays free.

    :param structure: A compiled Input Sequence carrying at least one teleport keydown.
    :param ign: The character's in-game name, used to resolve both key binds.
    :param teleport_skill: The teleport being cast through; its `animation_time` is the
        re-press cadence.
    :param ultimate_skill: The skill to fuse into the teleport regions.
    :return: A new, truncated Input Sequence carrying the rebuilt regions.
    """
    teleport_key = teleport_skill.key_bind(ign)
    ultimate_key = ultimate_skill.key_bind(ign)
    result = controller.KeyboardInputWrapper(
        structure.handle,
        forced_key_releases=structure.forced_key_releases,
        initial_held_keys=structure.initial_held_keys,
    )
    if ultimate_key not in result.forced_key_releases:
        result.forced_key_releases.append(ultimate_key)

    regions = _teleport_regions(structure, teleport_key)
    idx = 0
    while idx < len(structure.keys):
        stop = regions.get(idx)
        if stop is None:
            result.append(
                structure.keys[idx], structure.events[idx], structure.delays[idx]
            )
            idx += 1
            continue
        # The region's own duration is the budget: everything the rebuild needs is
        # already in the compiled sequence.
        budget = sum(structure.delays[idx:stop]) + controller.OVERHEAD * (stop - idx)
        _append_telecast_taps(
            result, teleport_key, ultimate_key, budget, teleport_skill.animation_time
        )
        idx = stop
    return result.truncate(ultimate_skill.animation_time)


def telecast_compiler(
    initial_held_keys: frozenset[str] | None,
    *,
    movement_compiler: Callable[
        [frozenset[str] | None], controller.KeyboardInputWrapper | None
    ],
    handle: int,
    ign: str,
    teleport_skill: Skill,
    ultimate_skill: Skill,
    correlation_id: str | None = None,
) -> controller.KeyboardInputWrapper | None:
    """
    `telecast` in the shape `controller.compile_and_send` expects - a compiler that
    decorates another compiler.

    Telecasting is a post-processing pass over a compiled Input Sequence, so it has to
    run where the compile now happens: at dispatch, inside the focus lock (ADR 0002).
    It wraps `compile_movements` rather than becoming another of its parameters,
    because it is a second concern layered on the first, not a variation of it: the
    movement compile is unchanged and unaware, and the wrapper is an adapter at the
    same seam - `Callable[[frozenset[str] | None], KeyboardInputWrapper | None]` -
    that `compile_movements` and `cast_skill_compiler` already sit at. Taking the
    inner compiler as a parameter rather than naming `compile_movements` directly
    keeps this module free of any dependency on the mechanics layer (which imports
    it) and lets the caller freeze the plan exactly as rotation does.

    That seam survives `telecast` becoming a rebuild rather than an in-place rewrite:
    a region is still found in the compiled sequence, and its budget is still the
    region's own duration. The one thing the rebuild needs that no Input Sequence
    carries is the re-press cadence, and that arrives here as the teleport `Skill`
    rather than its key bind alone - a wider parameter at the wrapper, not a wider
    contract on the compiler it decorates.

    :param initial_held_keys: Movement keys held at dispatch, from the Held-Keys
        Ledger. Handed straight to the inner compiler, and to the fallback cast.
    :param movement_compiler: The compiler whose Input Sequence gets fused - in
        practice a `compile_movements` partial over the current Movement Plan.
    :param handle: The client window the sequence targets, for the fallback cast.
    :param ign: The character's in-game name.
    :param teleport_skill: The teleport whose regions get rebuilt; supplies both the
        key a teleport keydown Step carries and the re-press cadence.
    :param ultimate_skill: The skill to fuse in.
    :param correlation_id: The Correlation ID of the `_decide()` call that built this
        partial. Baked in by the caller because the compile happens in Main Process,
        where the decision that asked for it is no longer in scope - and the fallback
        below is a Telemetry Record only that decision explains.
    :return: The fused Input Sequence, or a plain cast when there is nothing to fuse.
    """
    structure = movement_compiler(initial_held_keys)
    if structure is None or not _has_keydown(structure, teleport_skill.key_bind(ign)):
        # Reachable even when the Movement Plan holds teleports: `total_duration` can
        # truncate the compile before the first teleport component is built. Casting
        # in place still hits the mobs, which is what this DecisionMaker is for.
        unavailable: TelecastUnavailablePayload = {
            "ultimate_skill": ultimate_skill.name,
            "reason": "no_compiled_sequence" if structure is None else "no_teleport",
        }
        emit_event(
            correlation_id,
            COMBAT_TELECAST_UNAVAILABLE,
            unavailable,
            logger_name=logger.name,
        )
        return cast_skill(
            handle, ign, ultimate_skill, initial_held_keys=initial_held_keys
        )
    return telecast(structure, ign, teleport_skill, ultimate_skill)


def random_jump(handle: int, jump_key: str) -> controller.KeyboardInputWrapper:
    """
    Builds a jump in a random direction, releasing whatever is currently held first.
    That release is sent immediately, so this must be called from Main Process - build
    it inside the ActionRequest procedure rather than when composing the request.
    """
    direction = random.choice(["left", "right"])
    controller.release_all(handle)
    structure = single_jump(handle, direction, jump_key)
    structure.forced_key_releases.append(direction)
    return structure
