import random
from typing import Literal

from botting import controller
from botting.models_abstractions import Skill

FIRST_DELAY = 0.5


def _resolve_held_keys(
    structure: controller.KeyboardInputWrapper | None,
    handle: int,
    initial_state: controller.InputState | None,
) -> set[str]:
    """
    Determines the movement keys held before this builder call starts.
    Chains onto `structure` when one exists (no live query needed); otherwise defers to
    `initial_state` when supplied, and only falls back to the live Win32 query when
    neither is available - so a caller providing either keeps compilation deterministic.

    The `H0` half of the start state. Its `T0` half - which of those keys may legally
    repeat - is `structure.typematic_owner` / `initial_state.typematic_owner`, read
    where a builder needs it rather than folded in here: this answers "what is down".
    """
    if structure is not None:
        return structure.keys_held
    if initial_state is not None:
        return set(initial_state.held_keys)
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
#             held_keys, ["keyup"] * len(held_keys), next(controller.random_delay)
#         )
#     return _initial_structure


def move(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    secondary_direction: Literal["left", "right", "up", "down"] | None = None,
    *,
    duration: float,
    structure: controller.KeyboardInputWrapper | None = None,
    release_keys: str | list[str] | None = None,
    initial_state: controller.InputState | None = None,
) -> controller.KeyboardInputWrapper:
    """
    Creates the input structures and delays to describe the movement.
    If the movement extends on a previous input, the input structures and delays are
    appended onto the FocusedInput instance.
    :param handle:
    :param direction:
    :param secondary_direction: A second direction held for the same duration, always
        perpendicular to `direction` in practice - a walk carries up/down for the
        rope or portal it is heading into, a climb carries left/right. Both axes are
        accepted because both are used; the body treats it symmetrically with
        `direction` and assumes nothing about which axis it is on.
    :param duration:
    :param structure:
    :param release_keys: If specified, release events are inserted before the movement,
        provided the release_keys are held.
    :param initial_state: The keyboard state to assume when `structure` is None - held
        movement keys, typematic owner and how long it has owned - instead of querying
        the live Win32 state. Enables deterministic offline compilation of a movement
        plan's first builder call.
    :return:
    """
    initial_duration = getattr(structure, "duration", 0)
    keys_held = _resolve_held_keys(structure, handle, initial_state)
    repeated_key: str = secondary_direction or direction
    limit = initial_duration + duration
    if isinstance(release_keys, str):
        release_keys = [release_keys]

    first_keys = [direction]
    if secondary_direction:
        first_keys.append(secondary_direction)
    first_delay = (
        # TODO - see if "not in keys_held + ["up"]" is necessary and if so, document why
        # if repeated_key not in list(structure.keys_held) + ["up"]
        min(FIRST_DELAY, duration)
        if repeated_key not in keys_held
        else next(controller.random_delay)
    )
    # A keydown for a key already down is a repeat, not a press (**A7**), so a
    # Continuation arriving with the direction still held presses nothing and lets the
    # fill carry the time. Splitting on a per-key basis - rather than the old
    # all-or-nothing `needs_press`, which pressed every key in `first_keys` the moment
    # any one of them needed it - matters once `first_keys` carries a
    # secondary_direction: a Continuation on `direction` alone must press only the
    # secondary key, or the already-owned `direction` gets an illegal repeat
    # (issue #132).
    keys_to_press = [key for key in first_keys if key not in keys_held]
    if structure is None:
        release_index = 0
        first_steps: list[str | list[str]] = list(keys_to_press)
        first_downs: list[controller.EVENTS | list[controller.EVENTS]] = [
            "keydown"
        ] * len(first_steps)
        # One delay per Step. `[first_delay]` alone left a two-key opening press - a
        # walk into a climb or a portal, which carries a secondary direction - with two
        # Steps and one delay: an **A1 Shape** violation, and an IndexError on
        # `delays[i]` in the send loop. Only the opening Step carries the typematic
        # delay; the second key follows at the ordinary input cadence.
        first_delays = [first_delay] + [
            next(controller.random_delay) for _ in first_steps[1:]
        ]
        structure = controller.KeyboardInputWrapper(
            handle,
            first_steps,
            first_downs,
            first_delays if first_steps else [],
            initial_state=initial_state,
        )
    else:
        release_index = len(structure.keys)
        if keys_to_press:
            downs: list[controller.EVENTS] = ["keydown"] * len(keys_to_press)
            structure.append(keys_to_press, downs, first_delay)

    if release_keys:
        # `_clear_opposites` (triggered by the press above, in `append`/`__post_init__`)
        # already releases the opposite of anything in `keys_to_press` that is held -
        # exactly what `release_keys` exists to do for a `secondary_direction`'s
        # opposite (`compile_movements`' WALK_* case: `secondary="up"` pairs with
        # `release_keys="down"`). Excluding those here is what keeps the two
        # mechanisms from both releasing the same key: one phantom release (**A6**)
        # sandwiching the real press between two releases at a stale `release_index`
        # (issue #132).
        cleared_by_press = {
            controller.OPPOSITES[key]
            for key in keys_to_press
            if key in controller.OPPOSITES
        } & keys_held
        actual_releases = list((set(release_keys) & keys_held) - cleared_by_press)
        if actual_releases:
            ups: list[controller.EVENTS] = ["keyup"] * len(actual_releases)
            structure.insert(
                release_index,
                actual_releases,
                ups,
                next(controller.random_delay),
            )
    structure.fill(repeated_key, "keydown", controller.typematic_delay, limit=limit)
    return structure


def single_jump(
    handle: int,
    direction: Literal["left", "right", "up", "down"],
    jump_key: str,
    structure: controller.KeyboardInputWrapper | None = None,
    repeat_key: str | None = None,
    initial_state: controller.InputState | None = None,
    *,
    duration: float,
    off_rope: bool = False,
) -> controller.KeyboardInputWrapper:
    """
    One jump: the direction pressed (unless already held), the jump key tapped,
    then the direction held through the flight.

    :param duration: The jump's flight, seconds from take-off (the jump key's
        press) to landing, as the `FootholdGraph` traced it from `VRPhysics`. The
        jump key's tap counts towards it, and so do the two `OVERHEAD`s the send
        loop spends on the press and the release: the Step after the jump goes
        out at the landing, so the walk or the jump after it starts on time
        however loaded the machine is (#589). Before, every key after a jump
        went down two `OVERHEAD`s late, and the second jump of a chain off a
        ledge's open end went down past it.
    :param off_rope: The jump takes off sideways from a rope or a ladder. A climb
        key still down (`up` or `down`, a climb cut at the Action cap or the
        climb just before) comes up first, with the gap `jump_on_rope` leaves
        after its own releases: with `down` held, the client climbs on down the
        rope and never takes the jump (#561: 56 of 64 jumps keyed so on the
        descent stayed on it, and 7 of the 8 others left it at its bottom).
    """
    keys_held = _resolve_held_keys(structure, handle, initial_state)
    if off_rope and direction in ("left", "right"):
        for key in sorted(keys_held & {"up", "down"}):
            gap = next(controller.random_delay) * 5
            if structure is None:
                structure = controller.KeyboardInputWrapper(
                    handle, [key], ["keyup"], [gap], initial_state=initial_state
                )
            else:
                structure.append(key, "keyup", gap)
    first_keys = [direction, jump_key] if direction not in keys_held else [jump_key]
    if structure is None:
        first_steps: list[str | list[str]] = list(first_keys)
        first_downs: list[controller.EVENTS | list[controller.EVENTS]] = [
            "keydown"
        ] * len(first_keys)
        structure = controller.KeyboardInputWrapper(
            handle,
            first_steps,
            first_downs,
            [next(controller.random_delay) * 2] * len(first_keys),
            initial_state=initial_state,
        )
    else:
        for key in first_keys:
            structure.append(key, "keydown", next(controller.random_delay))
    # The take-off is the jump key's press: its tap is already part of the flight,
    # as is the `OVERHEAD` the send loop spends after the press and after the release.
    flight = max(duration - structure.delays[-1] - 2 * controller.OVERHEAD, 0.0)
    if repeat_key is not None:
        structure.fill(
            repeat_key,
            "keydown",
            controller.typematic_delay,
            limit=flight + structure.duration,
        )
        if repeat_key not in structure.forced_key_releases:
            structure.forced_key_releases.append(repeat_key)
    structure.append(jump_key, "keyup", flight)
    structure.forced_key_releases.append(jump_key)
    return structure


def jump_on_rope(
    handle: int,
    direction: Literal["left", "right"],
    jump_key: str,
    structure: controller.KeyboardInputWrapper | None = None,
    initial_state: controller.InputState | None = None,
    *,
    duration: float,
) -> controller.KeyboardInputWrapper:
    """
    Jump on a rope. The secondary direction is maintained after the jump.
    :param handle:
    :param direction:
    :param jump_key:
    :param structure:
    :param initial_state: The keyboard state to assume when `structure` is None -
        held movement keys, typematic owner and how long it has owned - instead of
        querying the live Win32 state.
    :param duration: Seconds from take-off to the grab, as the `FootholdGraph`
        traced the arc from `VRPhysics`: the jump key and `up` are held that long.
    :return:
    """
    if structure is None:
        structure = controller.KeyboardInputWrapper(
            handle,
            [direction],
            ["keydown"],
            [next(controller.random_delay)],
            initial_state=initial_state,
        )

    for key in structure.keys_held:
        if key == direction:
            continue
        # Longer delay to try preventing "static" jumps
        structure.append(key, "keyup", next(controller.random_delay) * 5)

    if direction not in structure.keys_held:
        structure.append(direction, "keydown", next(controller.random_delay) * 5)

    structure.append([jump_key, "up"], ["keydown", "keydown"], duration)

    # The press above can itself release `direction`: `_clear_opposites` drops the
    # opposite of any key about to go down, and "up"'s opposite is "down" - the
    # value a JUMP_DOWN call site passes as `direction` (issue #131). Releasing it
    # again unconditionally below would double-release a key `_clear_opposites`
    # already closed the Hold on, so re-check `keys_held` rather than assume this
    # function's own press left it untouched.
    release_keys: list[str] = [jump_key]
    release_events: list[controller.EVENTS] = ["keyup"]
    if direction in structure.keys_held:
        release_keys.append(direction)
        release_events.append("keyup")
    structure.append(release_keys, release_events, next(controller.random_delay) * 2)

    structure.forced_key_releases.append(jump_key)
    return structure


def jump_up_on_rope(
    handle: int,
    jump_key: str,
    structure: controller.KeyboardInputWrapper | None = None,
    initial_state: controller.InputState | None = None,
    *,
    duration: float,
) -> controller.KeyboardInputWrapper:
    """
    Jump straight up into a rope's bottom, from right under it (#111): every
    other held key released first, as `jump_on_rope` does, then the jump key
    and `up` pressed together and held for the flight to the rope, then the
    jump key released. `up` stays held, into the climb.

    :param duration: Seconds from take-off to the grab, as the `FootholdGraph`
        traced it from `VRPhysics`.
    """
    if structure is None:
        structure = controller.KeyboardInputWrapper(
            handle, [], [], [], initial_state=initial_state
        )
    for key in sorted(structure.keys_held):
        if key == "up":
            continue
        # Longer delay to try preventing "static" jumps, as `jump_on_rope`.
        structure.append(key, "keyup", next(controller.random_delay) * 5)
    if "up" in structure.keys_held:
        structure.append(jump_key, "keydown", duration)
    else:
        structure.append([jump_key, "up"], ["keydown", "keydown"], duration)
    structure.append(jump_key, "keyup", next(controller.random_delay) * 2)
    structure.forced_key_releases.append(jump_key)
    return structure


def teleport(
    handle: int,
    ign: str,
    direction: Literal["left", "right", "up", "down"],
    teleport_skill: Skill,
    num_times: int = 1,
    structure: controller.KeyboardInputWrapper | None = None,
    repeat_key: str | None = None,
    initial_state: controller.InputState | None = None,
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
    :param initial_state: The keyboard state to assume when `structure` is None -
        held movement keys, typematic owner and how long it has owned - instead of
        querying the live Win32 state.
    :return:
    """
    initial_duration = getattr(structure, "duration", 0)
    keys_held = _resolve_held_keys(structure, handle, initial_state)
    limit = initial_duration + teleport_skill.animation_time * num_times
    # Opens empty and lets the single guarded press below do the work. Constructing
    # with `[direction] keydown` pressed unconditionally: an illegal repeat (**A7**)
    # when the direction was already held, and a redundant double press when it was
    # not, since the guarded append fires straight afterwards.
    if structure is None:
        structure = controller.KeyboardInputWrapper(
            handle, [], [], [], initial_state=initial_state
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
            controller.typematic_delay,
            limit=limit,
        )
        # The fill leaves the skill key down; release it here rather than relying on
        # the forced volley, so the sequence closes its own Holds and a following
        # component does not run with the teleport key latched. Guarded because
        # `fill` stops on absolute duration and can legitimately emit no Step at all,
        # and a keyup for a key never pressed is a phantom release.
        if teleport_skill.key_bind(ign) in structure.keys_held:
            structure.append(
                teleport_skill.key_bind(ign), "keyup", next(controller.random_delay)
            )
    else:
        structure.append(
            teleport_skill.key_bind(ign), "keydown", next(controller.random_delay)
        )
        structure.append(
            teleport_skill.key_bind(ign), "keyup", next(controller.random_delay)
        )
        structure.fill(repeat_key, "keydown", controller.typematic_delay, limit=limit)
    if direction == "down" and direction not in structure.forced_key_releases:
        structure.forced_key_releases.append(direction)
    if teleport_skill.key_bind(ign) not in structure.forced_key_releases:
        structure.forced_key_releases.append(teleport_skill.key_bind(ign))
    return structure


def random_jump(
    handle: int, jump_key: str, duration: float
) -> controller.KeyboardInputWrapper:
    """
    Builds a jump in a random direction, releasing whatever is currently held first.
    That release is sent immediately, so this must be called from Main Process - build
    it inside the ActionRequest procedure rather than when composing the request.

    :param duration: The jump's flight: a jump that lands back at its take-off's
        height, `VRPhysics.jump_duration` with the character's current stats.
    """
    directions: tuple[Literal["left"], Literal["right"]] = ("left", "right")
    direction = random.choice(directions)
    controller.release_all(handle)
    structure = single_jump(handle, direction, jump_key, duration=duration)
    structure.forced_key_releases.append(direction)
    return structure
