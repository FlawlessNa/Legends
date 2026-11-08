"""
The engine layer's Event Types and payload types.

An **Event Type** is the stable, semantic name of what a Telemetry Record
describes - the key an offline analyzer groups on. It is a dotted
``<area>.<event>`` string in ``snake_case``, where the area is a behaviour
domain worth filtering a Session on::

    action.scheduled        decision.disabled

The area list is an **open set**: a new area arrives by adding a constant here,
and there is no central registry to keep in step. It is deliberately *not* the
four Log Buckets - those partition code for routing and carry a catch-all
``other``, which is dead weight as a grouping key.

This module holds the areas the *generic engine* owns, and only those. The game
layer keeps its own in ``maple/telemetry_events.py``, for the same reason
``botting/`` never imports ``maple/``: making the engine enumerate a game's
events inverts the dependency. Areas here:

* ``action`` - an ``ActionRequest``'s life once it reaches Main Process. These
  are the records that close the Correlation ID chain: the DecisionMaker end
  says what was decided, and these say what became of it.
* ``decision`` - one ``DecisionMaker`` gating another.
* ``session`` - the Session itself: what it ran, and why it ended.
  ``session.ended`` is the last record written. ``session.started`` comes
  before every Engine's records, but not necessarily first: a process started
  in ``SessionManager.__enter__``, such as Peripherals, can emit before
  ``launch`` emits it. A reader must not assume it is the first line
  (``botting.session`` gives those records a negative time).

Every Producer passes a constant from a module like this one, never a literal,
and builds its payload through the matching ``TypedDict``. ``emit_event()``'s
signature stays permissive on purpose - the typing is the Producer's discipline,
not the transport's, because telemetry may never raise inside the thing it is
observing. Payloads carry **JSON primitives only**, converted at the call site.
"""

from typing import Final, Literal, TypedDict

# --- action ---------------------------------------------------------------
#: A request won its priority contest and its task was created.
ACTION_SCHEDULED: Final = "action.scheduled"
#: A request lost its priority contest but asked to be tried again later.
ACTION_REQUEUED: Final = "action.requeued"
#: A request lost its priority contest and was dropped.
ACTION_BLOCKED: Final = "action.blocked"
#: A request superseded an in-flight task carrying its own identifier.
ACTION_SELF_CANCELLED: Final = "action.self_cancelled"
#: A request cancelled a *different* task on its way to being scheduled.
ACTION_CANCELS_OTHER: Final = "action.cancels_other"
#: A scheduled request's task ended: it completed, was cancelled, or raised.
#: Exactly one per task created, so every ``action.scheduled`` that got as far
#: as a task has one. The exception is a request whose procedure raises when it
#: is *called* - a Discord kill raises ``KeyboardInterrupt`` synchronously in
#: ``_schedule_task``, before any task exists - so it is scheduled but never
#: finished. That is expected: the Session ends there, and ``session.ended``
#: says how.
ACTION_FINISHED: Final = "action.finished"

# --- decision -------------------------------------------------------------
#: A DecisionMaker suspended another one, across every Engine.
DECISION_DISABLED: Final = "decision.disabled"
#: A DecisionMaker resumed another one, across every Engine.
DECISION_ENABLED: Final = "decision.enabled"

# --- session --------------------------------------------------------------
#: The Session knows every Bot it runs; emitted before any Engine starts.
SESSION_STARTED: Final = "session.started"
#: Something outside the bot asked the Session to stop (the stop file).
SESSION_STOP_REQUESTED: Final = "session.stop_requested"
#: The Session is exiting. The last record Main Process writes before the
#: telemetry sink closes.
SESSION_ENDED: Final = "session.ended"

#: How a scheduled task ended. ``raised`` is any exception but cancellation.
ActionOutcome = Literal["completed", "cancelled", "raised"]
#: Why a Session ended. A failing task counts as ``error`` even though
#: ``SessionManager.launch`` returns normally after one.
SessionEndCause = Literal["completed", "stop_file", "interrupted", "error"]


class ActionPayload(TypedDict):
    """The request itself, for every ``action.*`` event but one."""

    identifier: str
    priority: int


class ActionCancelsOtherPayload(TypedDict):
    """``action.cancels_other``: the canceller and its victim."""

    identifier: str
    cancelled: str


class DecisionGatePayload(TypedDict):
    """``decision.disabled`` / ``decision.enabled``: who was gated."""

    target: str


class ActionFinishedPayload(TypedDict):
    """``action.finished``: which task ended, how, and how long it ran."""

    identifier: str
    outcome: ActionOutcome
    elapsed_ms: int


class SessionBotPayload(TypedDict):
    """One Bot of a Session, as ``session.started`` lists it."""

    ign: str
    bot_class: str
    #: The DecisionMaker class names, in the Bot's own order.
    decision_makers: list[str]


class SessionStartedPayload(TypedDict):
    """``session.started``: every Bot the Session runs, and its mode."""

    bots: list[SessionBotPayload]
    debug: bool


class SessionStopRequestedPayload(TypedDict):
    """``session.stop_requested``: the reason the requester gave."""

    reason: str


class SessionEndedPayload(TypedDict):
    """``session.ended``: why, and the error when there was one."""

    cause: SessionEndCause
    #: ``"<ExceptionType>: <message>"`` when ``cause`` is ``error``, else null.
    error: str | None
