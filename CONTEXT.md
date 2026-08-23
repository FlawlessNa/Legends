# Legends

A MapleStory botting framework. `botting/` is the generic engine (process
orchestration, input control, logging); `maple/` is the game-specific layer
(movement, decision-making, minimap model) built on top of it.

## Language

**Session**:
One run of the bot, from `SessionManager` creation (spawning the `Engine`,
`PeripheralsProcess`, and child task processes) through teardown. All logging
and telemetry for a run is scoped to its Session — one Session, one log
directory.
_Avoid_: Run, execution — "Session" is the existing term (`SessionManager`,
`botting/core/session_manager.py`); don't introduce a synonym for it.

**Telemetry Record**:
One JSONL line describing a single decision or action a `DecisionMaker`
made and why: `{timestamp, correlation_id, logger_name, event_type,
payload}`. Distinct from a text-log line — text logs carry narrative
(warnings, errors, lifecycle); Telemetry Records carry the diagnostic
"what did the bot decide and why," meant for machine analysis, not eyeballing.
_Avoid_: Log entry, event log — both blur the record/narrative-log
distinction this concept exists to make.

**Correlation ID**:
A `uuid.uuid4()` generated once at the top of the `DecisionMaker._decide()`
call that triggered a chain of behavior, and passed explicitly to every
Telemetry Record emitted as a result — ties a decision to whatever it caused
(e.g. a resulting movement action) into one traceable chain.
_Avoid_: Action ID — collides with the existing `ActionRequest` type.

**Producer**:
A subsystem that emits Telemetry Records via `emit_event()`. Movement is the
first Producer; any `DecisionMaker` subclass can become one.

## Movement compilation

**Path**:
The ordered minimap cells leading from the character's current position to its
target, as produced by pathfinding over the minimap grid.
_Avoid_: Route — "route cycle" already means the repeating decide-and-move loop,
not the cells themselves.

**Movement Plan**:
The Path expressed as game-level intent — a sequence of typed movements with
lengths, e.g. walk right 5, jump left 1. The last layer that still speaks in
terms of what the character does rather than which keys are sent.
_Avoid_: Movements, movement list.

**Input Sequence**:
A Movement Plan compiled down to a keystroke script: the ordered keys, events
and delays that will be handed to `SendInput`, plus the keys declared for forced
release. Deterministic given a map config, a start, an end, and the keys held
going in.
_Avoid_: Action, structure, input structure — "Action" is a different thing
(below), and `structure` is the local variable name, not the concept.

**Action**:
The request a DecisionMaker sends to Main Process asking it to execute an Input
Sequence, carrying the priority and cancellation rules Main Process arbitrates
by.
_Avoid_: Using "action" for the Input Sequence itself — the `data.action`
attribute holds an Input Sequence and is a misnomer.

**Step**:
One position in an Input Sequence: the key or keys sent simultaneously at that
position, their events, and the delay waited afterwards. Keys sent together in
one Step reach the game as a single batch.
_Avoid_: Keystroke, frame — a Step may carry several keys, may be a release, and
has no fixed duration.

**Hold**:
The span during which one key stays down — from the Step that presses it to the
Step that releases it, measured in elapsed seconds. Not readable from any single
Step; it is derived by walking the Input Sequence.
_Avoid_: Press, interval, hold window.

**Delivered Prefix**:
The portion of an Input Sequence the game actually received, plus whatever the
forced releases fired afterwards. Diverges from the Input Sequence whenever
compilation truncated it at a duration limit or a higher-priority Action
cancelled it mid-flight.
_Avoid_: Sent inputs, partial sequence.

**Held-Keys Ledger**:
The authoritative per-client record of the keys the bot has pressed and not
yet released — owned by the sole process that sends input, updated as each
Step is delivered, and reconciled against the physical keyboard state at
session start and at every client focus switch. It is the "keys held going
in" that live compilation reads. At most one client's entry is non-empty:
the currently focused one.
_Avoid_: held-keys state, keys sent — the historical set of every key ever
sent answers a different question than what is down right now.

## Movement checking

**Invariant**:
A property of an Input Sequence, or of a pair of them, that must always hold —
decidable offline with no measured constant. A violation is a defect, and it
gates the movement lab suite.
_Avoid_: Rule, assertion, constraint.

**Expectation**:
A property that holds only within a tolerance, or only against constants that
must be measured from the live game. A violation is reported for review rather
than failing the suite.
_Avoid_: Soft invariant, warning, heuristic.

**Continuation**:
The handoff where one Input Sequence reached its end and the next was compiled
afterwards from the resulting position, inheriting whatever keys were left down.
The normal route-cycle boundary; carrying a direction key across it is
deliberate, and avoids a stop-start stutter.
_Avoid_: Chaining, follow-on.

**Preemption**:
The handoff where a higher-priority Action cancelled an Input Sequence
mid-flight, ending its Delivered Prefix at an arbitrary Step. Always originates
from a different DecisionMaker — a route cycle can never preempt itself.
_Avoid_: Interrupt, cancellation — "cancellation" is the mechanism, Preemption
is the handoff it produces.
