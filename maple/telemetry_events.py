"""
The game layer's Event Types and payload types.

An **Event Type** is the stable, semantic name of what a Telemetry Record
describes - the key an offline analyzer groups on. It is a dotted
``<area>.<event>`` string in ``snake_case``, where the area is a behaviour
domain worth filtering a Session on::

    recovery.map_check_failed       inventory.shop_opened

The area list is an **open set**: a new area arrives by adding a constant here,
and there is no central registry to keep in step. It is deliberately *not* the
four Log Buckets - those partition code for routing and carry a catch-all
``other``, which is dead weight as a grouping key. Areas so far:

* ``recovery`` - the bot noticed it was in a bad state and did something about
  it.
* ``combat`` - what the bot chose to hit, and with what.
* ``inventory`` - the trip to town, milestone by milestone.
* ``rebuff`` - the cross-Engine handshake that gets a party buffed together.
* ``chat`` - lines read in the chat log that the bot reacts to.
* ``movement`` - Movement Plans started and targets reached, with deliberately
  minimal fields (#331). The movement-framework map may add records but not
  repurpose these. ``rotation`` stays reserved for that map.
* ``state`` - where the character was, sampled on a clock rather than on an
  event.
* ``position`` - each read of the character's virtual position, whatever it
  read (#392).

This module sits at the package root rather than under ``decision_makers/`` or
``model/`` because movement telemetry is assembled across both - anywhere
deeper invites a circular import. The engine layer keeps its own constants in
``botting/telemetry_events.py``; neither module imports the other.

Every Producer passes a constant from a module like this one, never a literal,
and builds its payload through the matching ``TypedDict``. ``emit_event()``'s
signature stays permissive on purpose - the typing is the Producer's discipline,
not the transport's, because telemetry may never raise inside the thing it is
observing. Payloads carry **JSON primitives only**, converted at the call site:
an ``int()`` around anything a numpy pipeline produced, a ``Box`` decomposed
into named fields rather than handed over whole.
"""

import math
from collections.abc import Iterable, Sequence
from typing import Any, Final, SupportsInt, TypedDict

# --- recovery -------------------------------------------------------------
#: The in-map check failed; the minimap is being toggled to clear it.
RECOVERY_MAP_CHECK_FAILED: Final = "recovery.map_check_failed"
#: The in-map check passed on the retry - the bot was in the map all along.
RECOVERY_MAP_CHECK_RECOVERED: Final = "recovery.map_check_recovered"
#: Mobs reappeared while the mob-spawn failsafe was rotating, so normal
#: operation resumes. Its *start* stays a text-log warning: something is wrong
#: at that point and a human wants to see it.
RECOVERY_MOB_SPAWN_RESTORED: Final = "recovery.mob_spawn_restored"
#: A Stuck detector fired (CONTEXT.md -> Movement recovery). One record per
#: firing, whatever the Reaction Ladder then does with it - Trial analysis and
#: live detection read this same signal.
RECOVERY_STUCK_DETECTED: Final = "recovery.stuck_detected"
#: The Reaction Ladder's first rung: keys released, brief pause, random jump.
RECOVERY_REFLEX: Final = "recovery.reflex"
#: The Reaction Ladder's second rung: the target is dropped. The payload names
#: the suspected grid connection - attribution for #120's defect filing.
RECOVERY_ABANDON: Final = "recovery.abandon"
#: The Reaction Ladder's last rung: the bot pauses with keys released and waits
#: for a human resume.
RECOVERY_ESCALATE: Final = "recovery.escalate"
#: A Reaction Ladder that had advanced was reset - by real progress, or by a
#: natural target change.
RECOVERY_LADDER_RESET: Final = "recovery.ladder_reset"

# --- combat ---------------------------------------------------------------
#: Enough mobs were in range, so the training skill is being cast.
COMBAT_MOBS_HIT: Final = "combat.mobs_hit"
#: The training skill is being fused into the movement about to be dispatched.
COMBAT_TELECAST: Final = "combat.telecast"
#: Telecast was chosen but the compiled sequence held no teleport to fuse into,
#: so the ultimate is cast in place instead. Emitted from Main Process, at
#: dispatch, which is the only place the truncated compile is visible.
COMBAT_TELECAST_UNAVAILABLE: Final = "combat.telecast_unavailable"

# --- inventory ------------------------------------------------------------
#: The inventory filled up and the trip to town has begun.
INVENTORY_CLEANUP_STARTED: Final = "inventory.cleanup_started"
#: The character reached the spot it casts its door from.
INVENTORY_DOOR_SPOT_REACHED: Final = "inventory.door_spot_reached"
#: The character came out of the door and is in town.
INVENTORY_TOWN_REACHED: Final = "inventory.town_reached"
#: The NPC shop is open and ready to be sold into.
INVENTORY_SHOP_OPENED: Final = "inventory.shop_opened"
#: The target tab is empty.
INVENTORY_CLEARED: Final = "inventory.cleared"
#: The character is back in its original map with rotation restored.
INVENTORY_CLEANUP_COMPLETED: Final = "inventory.cleanup_completed"

# --- rebuff ---------------------------------------------------------------
#: This member declared it is time for the party to rebuff.
REBUFF_SIGNALLED: Final = "rebuff.signalled"
#: Every member is within range of the rebuff location.
REBUFF_MEMBERS_IN_POSITION: Final = "rebuff.members_in_position"
#: Every member's buffs are up; the handshake is over.
REBUFF_PARTY_COMPLETE: Final = "rebuff.party_complete"
#: The shared ready state was cleared, ending one rebuff round.
REBUFF_STATE_RESET: Final = "rebuff.state_reset"

# --- chat -----------------------------------------------------------------
#: A GM's line appeared in the chat log. One record per line, the first time
#: it is read; ``ChatWatch`` raises the alarm on it.
CHAT_GM_LINE: Final = "chat.gm_line"

# --- movement -------------------------------------------------------------
#: Rotation is about to ship a Movement Plan.
MOVEMENT_PLAN_STARTED: Final = "movement.plan_started"
#: A rotation mode judged that the character reached its target.
MOVEMENT_TARGET_REACHED: Final = "movement.target_reached"

# --- state ----------------------------------------------------------------
#: A periodic sample of where the character is and where it is heading.
STATE_SNAPSHOT: Final = "state.snapshot"

# --- position -------------------------------------------------------------
#: The character's virtual position was read: one record per read of
#: ``current_position``, ``UNSURE`` ones included, so an analyzer can count
#: reads per source and time how long the position stayed unsure.
POSITION_READ: Final = "position.read"


class MapCheckPayload(TypedDict):
    """``recovery.map_check_*``: the map the check was made against."""

    map_name: str


class MobSpawnRestoredPayload(TypedDict):
    """``recovery.mob_spawn_restored``: what the failsafe was watching for."""

    alert_timer: float
    alert_threshold: int


class StuckDetectedPayload(TypedDict):
    """
    ``recovery.stuck_detected``: which symptom, aimed at what, and by how much.

    ``measure`` and ``threshold`` are in the symptom's own unit - gated seconds
    for Stall/Stagnation/Target Timeout, repeat count for Plan Churn, wall
    seconds for Starvation - so an analyzer can read how decisively a detector
    fired without re-deriving its window.
    """

    symptom: str
    target_x: int
    target_y: int
    measure: float
    threshold: float


class ReactionPayload(TypedDict):
    """
    ``recovery.reflex`` / ``recovery.abandon`` / ``recovery.escalate``: which
    symptom advanced the ladder, and the suspected grid connection when the
    Movement Plan named one. Suspect fields are None when no plan was in hand.
    """

    symptom: str
    target_x: int
    target_y: int
    reflex_attempt: int
    abandon_count: int
    suspected_movement: str | None
    suspected_start_x: int | None
    suspected_start_y: int | None
    suspected_end_x: int | None
    suspected_end_y: int | None


class LadderResetPayload(TypedDict):
    """``recovery.ladder_reset``: why an engaged ladder was reset."""

    reason: str
    target_x: int
    target_y: int


class MobsHitPayload(TypedDict):
    """``combat.mobs_hit``: how many mobs, and which way the cast faces."""

    mob_count: int
    direction: str | None


class TelecastPayload(TypedDict):
    """``combat.telecast``: the two skills being fused."""

    teleport_skill: str
    ultimate_skill: str


class TelecastUnavailablePayload(TypedDict):
    """``combat.telecast_unavailable``: which fallback branch was taken."""

    ultimate_skill: str
    reason: str


class InventoryCleanupPayload(TypedDict):
    """``inventory.cleanup_started``: how the character is getting to town."""

    method: str


class InventoryMilestonePayload(TypedDict):
    """Every other ``inventory.*`` event: whose trip this is."""

    ign: str


class RebuffPayload(TypedDict):
    """Every ``rebuff.*`` event: which member emitted it."""

    ign: str


class ChatLinePayload(TypedDict):
    """
    ``chat.gm_line``: what the line says, and where it was drawn.

    ``text`` is None when the line's text couldn't be read in full: the line's
    image goes to Discord instead, not into the record.
    """

    kind: str
    text: str | None
    row_top: int


class PlanStartedPayload(TypedDict):
    """
    ``movement.plan_started``: the Movement Plan being shipped, and from where to
    where. Each component is ``[movement_type, length]``, ``movement_type`` being
    the ``MovementTypes`` member name and ``length`` in minimap units, not time.
    """

    components: list[list[Any]]
    from_x: int
    from_y: int
    target_x: int
    target_y: int


class TargetReachedPayload(TypedDict):
    """``movement.target_reached``: the target, and how far off the character was."""

    target_x: int
    target_y: int
    distance: float


class StateSnapshotPayload(TypedDict):
    """``state.snapshot``: every field is None while its value is unknown."""

    x: int | None
    y: int | None
    target_x: int | None
    target_y: int | None
    on_screen_x: int | None
    on_screen_y: int | None


class PositionReadPayload(TypedDict):
    """
    ``position.read``: what the read gave, and what each read said
    (`maple.screen.position.Fusion`). Positions are in virtual px; a field is
    None when its read didn't give it.

    ``status`` is the Reading's status value (``read`` or ``unsure``);
    ``source`` is ``fused`` or ``coarse``, None unless read. ``found`` counts the
    characters found on screen, ``near`` those within the window around the
    minimap's position;
    ``by_tag`` says the finder could tell ours apart by its name tag, so only a
    character marked ours could be chosen; ``own_elsewhere`` that a character
    marked ours was found outside the window. ``detail`` is why,
    as the Reading says it.
    """

    status: str
    source: str | None
    x: float | None
    y: float | None
    minimap_x: int | None
    minimap_y: int | None
    camera_x: int | None
    camera_y: int | None
    found: int
    near: int
    by_tag: bool
    own_elsewhere: bool
    detail: str


def plan_started_payload(
    movements: Iterable[Any], position: Sequence[Any], target: Sequence[Any]
) -> PlanStartedPayload:
    """
    :param movements: ``_MovementComponent``s, each with ``movement_type`` and
        ``length``.
    :param position: The character's minimap position.
    :param target: The rotation's target.
    """
    return {
        "components": [
            [
                getattr(move.movement_type, "name", str(move.movement_type)),
                int(move.length),
            ]
            for move in movements
        ],
        "from_x": int(position[0]),
        "from_y": int(position[1]),
        "target_x": int(target[0]),
        "target_y": int(target[1]),
    }


def target_reached_payload(
    position: Sequence[Any], target: Sequence[Any]
) -> TargetReachedPayload:
    """
    :param position: The character's minimap position.
    :param target: The target it was judged to have reached.
    """
    return {
        "target_x": int(target[0]),
        "target_y": int(target[1]),
        "distance": float(math.dist(position, target)),
    }


def _as_int(value: SupportsInt | None) -> int | None:
    return None if value is None else int(value)


def state_snapshot_payload(
    position: Sequence[Any] | None,
    target: Sequence[Any] | None,
    on_screen: Sequence[Any] | None,
) -> StateSnapshotPayload:
    """
    :param position: The minimap position, or None if unknown.
    :param target: The rotation's target, or None if unknown.
    :param on_screen: The character's on-screen box ``(x1, y1, x2, y2)``, or None
        if unknown; reported as its centre.
    """
    on_screen_x = on_screen_y = None
    if on_screen is not None:
        x1, y1, x2, y2 = on_screen
        on_screen_x, on_screen_y = int((x1 + x2) / 2), int((y1 + y2) / 2)
    return {
        "x": _as_int(position[0]) if position is not None else None,
        "y": _as_int(position[1]) if position is not None else None,
        "target_x": _as_int(target[0]) if target is not None else None,
        "target_y": _as_int(target[1]) if target is not None else None,
        "on_screen_x": on_screen_x,
        "on_screen_y": on_screen_y,
    }
