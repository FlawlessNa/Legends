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
* ``movement`` and ``rotation`` are reserved for the movement map's telemetry;
  ``MovementPayload`` lands here alongside these, and its field list is issue
  #12's to decide.

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

from typing import Final, TypedDict

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
