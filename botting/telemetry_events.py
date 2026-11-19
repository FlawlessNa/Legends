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
* ``decision`` - one ``DecisionMaker`` gating another: Pauses, and the legacy
  shim's disable and enable.
* ``key`` - a key going down or up at a client, from Main Process where it is
  sent (`botting/controller/inputs/key_times.py`, #538). One record per
  transition, typematic repeats left out; ``t`` is on the frames' clock
  (``time.monotonic()``). Written just after the send, off the send loop, so
  the envelope's timestamp trails the payload's ``wall`` and a record can land
  after records emitted later: order key records by ``t``.
* ``llm`` - a request to the language model (``botting.llm``): which model,
  what it cost in tokens, how long it took and how it ended.
* ``recording`` - the screen recorder, in the Peripherals process: where the
  video is, and a checkpoint about once a second that maps the telemetry clock
  to a frame index (``botting.session`` cuts frames with them). Like
  ``session.started``, ``recording.started`` can precede it.
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

# --- data -----------------------------------------------------------------
#: A DecisionMaker took a Claim on a steerable Data Key: the key now serves the
#: value source it claimed, until a ``data.released`` with the same key, holder
#: and reason.
DATA_CLAIMED: Final = "data.claimed"
#: A DecisionMaker released its Claim on a Data Key: the key serves its
#: Provider's own value again.
DATA_RELEASED: Final = "data.released"

# --- decision -------------------------------------------------------------
#: A DecisionMaker suspended another one through the legacy shim,
#: ``_disable_decision_makers``. Within its own Bot; until #433, across every
#: Engine.
DECISION_DISABLED: Final = "decision.disabled"
#: A DecisionMaker resumed another one through the legacy shim,
#: ``_enable_decision_makers``. Within its own Bot; until #433, across every
#: Engine.
DECISION_ENABLED: Final = "decision.enabled"
#: A holder took a Pause on a DecisionMaker in its own Bot. The legacy shim
#: (``_disable_decision_makers``) emits ``decision.disabled`` instead.
DECISION_PAUSED: Final = "decision.paused"
#: A holder released its Pause on a DecisionMaker. The target runs again only
#: once no Pause on it is left, so a ``decision.resumed`` closes one
#: ``decision.paused``, not necessarily the target's whole pause.
DECISION_RESUMED: Final = "decision.resumed"

#: A DecisionMaker's decision loop raised: the DecisionMaker, the exception's type
#: and its message. The Bot ends on it, with `DecisionMakerCrashed`.
DECISION_CRASHED: Final = "decision.crashed"

# --- key ------------------------------------------------------------------
#: A key went down at a client: a keydown for a key the Held-Keys Ledger did not
#: hold. A keydown for a key already down (a typematic repeat) is not one.
KEY_DOWN: Final = "key.down"
#: A keyup was sent to a client. Every keyup is one, ``held`` saying whether the
#: ledger had the key down (not held: a straggler `release_all` found down).
KEY_UP: Final = "key.up"

# --- llm ------------------------------------------------------------------
#: One request to the language model ended, whatever the outcome.
LLM_REQUEST: Final = "llm.request"

# --- recording ------------------------------------------------------------
#: The recorder's writer is open; the video at ``path`` is being written.
RECORDING_STARTED: Final = "recording.started"
#: A frame was written; emitted every *config* ``FPS`` frames, which is about
#: once a second of capture.
RECORDING_CHECKPOINT: Final = "recording.checkpoint"

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
#: What sent a key: ``step``, a Step of an Input Sequence in the send loop;
#: ``release``, `release_keys` - a sequence's forced releases and the releases on
#: its cancellation, `release_all` (focus switch, Session start and end), a pause.
KeyCause = Literal["step", "release"]


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


class PausePayload(TypedDict):
    """``decision.paused`` / ``decision.resumed``: one Pause."""

    #: The paused DecisionMaker's class name.
    target: str
    #: The holding DecisionMaker, as its ``repr`` names it, or ``"user"``.
    holder: str
    reason: str


class ClaimPayload(TypedDict):
    """``data.claimed`` / ``data.released``: one Claim."""

    #: The claimed Data Key's name.
    key: str
    #: The holding DecisionMaker, as its ``repr`` names it.
    holder: str
    reason: str


class DecisionCrashedPayload(TypedDict):
    """``decision.crashed``: who crashed, and on what."""

    #: The crashed DecisionMaker, as its ``repr`` names it.
    decision_maker: str
    exception_type: str
    message: str


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


class KeyPayload(TypedDict):
    """``key.down``: which key, at which client, when, and why."""

    key: str
    #: The client window it was sent to.
    handle: int
    #: ``time.monotonic()`` when ``SendInput`` returned, seconds: the clock frames
    #: are captured on, so it lines up with a Reading's ``frame_time``.
    t: float
    #: ``time.time()`` at the same moment, seconds since the epoch.
    wall: float
    cause: KeyCause
    #: The Movement Plan component that produced the Step (its Provenance), or
    #: null: a release, a Step no component produced, or a sequence handed in
    #: already compiled.
    origin: int | None


class KeyUpPayload(KeyPayload):
    """``key.up``: as ``key.down``, and whether the key was down."""

    #: Whether the Held-Keys Ledger held the key before this keyup.
    held: bool


class LlmRequestPayload(TypedDict):
    """``llm.request``: the model asked, what it cost, and how the call ended."""

    model: str
    input_tokens: int
    #: Input tokens served from the prompt cache.
    cached_tokens: int
    output_tokens: int
    ms: int
    #: ``ok``, ``refused``, ``timeout`` or ``error`` (``botting.llm.Outcome``).
    outcome: str


class RecordingStartedPayload(TypedDict):
    """``recording.started``: the video file, and the frame rate it declares."""

    path: str
    #: The rate the file declares: config ``FPS`` times ``Multiplier``. The
    #: recorder captures at config ``FPS``, so this is not the capture rate.
    fps: float


class RecordingCheckpointPayload(TypedDict):
    """``recording.checkpoint``: the 0-based index of the frame just written."""

    frame_index: int
