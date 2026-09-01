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
A `uuid.uuid4()` identifying one `DecisionMaker._decide()` call, and carried by
every Telemetry Record that call caused — including the ones emitted in Main
Process once the resulting action is dispatched. Ties a decision to what it
caused into one traceable chain. Its span is exactly that one call: a behaviour
pursued across several consecutive calls is several Correlation IDs, stitched
back together offline by the analyzer rather than at runtime. A record with no
originating decision (Session startup, listener lifecycle) carries no
Correlation ID at all.
_Avoid_: Action ID — collides with the existing `ActionRequest` type. Also
avoid calling a multi-call behaviour "one correlation" — that unit is an
Attempt, and it is the analyzer's to reconstruct.

**Producer**:
A subsystem that emits Telemetry Records via `emit_event()`. Movement is the
first Producer; any `DecisionMaker` subclass can become one.

**Event Type**:
The stable, semantic name of what a Telemetry Record describes — a dotted
`<area>.<event>` string, where the area is a behaviour domain an analyzer would
filter a Session on (movement, rotation, recovery, inventory, rebuff, combat,
session). Deliberately redundant with `logger_name`: that field is a Python
module path, ideal for routing to a Log Bucket but churning whenever a file
moves, whereas an Event Type is the grouping key the offline analyzer is
written against, so it must outlive refactors. Governed by convention rather
than validated at runtime — telemetry is never allowed to raise inside a
Producer. Additive only: new Event Types are added freely, existing ones are
never removed or repurposed.
_Avoid_: Event name, log type — both suggest a label chosen per call site,
whereas an Event Type is a shared vocabulary the analyzer is written against.

**Log Bucket**:
The text-log file a record is routed to, derived from its logger name — one of
movement, inputs, decisions, or other, alongside a combined file carrying all
four. A partition of the code by area, never by severity; every record belongs
to exactly one Bucket.
_Avoid_: Subsystem — used loosely across the codebase for any package, whereas
a Log Bucket is specifically a routing destination.

**Console Threshold**:
The minimum severity a record must carry to appear on the live console, looked
up per logger name. Independent of what the log files capture, which is always
everything. Separates "do I want to watch this right now" from "how bad is
this" — the two questions the retired per-module `LOG_LEVEL` constants
conflated.
_Avoid_: Log level — a record's severity and its console visibility are
distinct dials, and one word for both is the confusion this term exists to
prevent.

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
The request a DecisionMaker sends to Main Process asking it to execute something
in a game client, carrying the priority and cancellation rules Main Process
arbitrates by. A movement Action carries the Movement Plan plus the inputs
needed to compile it, never a compiled Input Sequence — compilation happens at
dispatch, inside the focus lock (ADR 0002).
_Avoid_: Using "action" for the Input Sequence itself — the two were conflated
by a `data.action` attribute that held an Input Sequence, now gone from the live
path.

**Step**:
One position in an Input Sequence: the key or keys sent simultaneously at that
position, their events, and the delay waited afterwards. Keys sent together in
one Step reach the game as a single batch. The batch may be empty, in which case
the Step sends nothing and only its delay elapses — how an Input Sequence
expresses time passing while a key stays held.
_Avoid_: Keystroke, frame — a Step may carry several keys, may carry none, may be
a release, and has no fixed duration.

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

**Typematic ownership**:
The entitlement, held by at most one key at a time, to be the one Windows repeats
while it stays down. A keydown claims it, a later keydown takes it away, and any
keyup ends repetition outright rather than handing it back to a key still held.
Carried across route-cycle boundaries beside the Held-Keys Ledger, because a set
of held keys does not say which of them may legally repeat.
_Avoid_: Auto-repeat, key repeat — those name the repeating itself, not which key
is entitled to it.

**Telecast**:
A movement and a skill cast performed as one: the teleport and the ultimate are
pressed together, released, and pressed again one teleport animation later, so
the character casts while it blinks. A post-processing pass over a finished Input
Sequence rather than a builder — it runs at dispatch, wrapped around the movement
compiler, and truncates the result to the skill's animation time.
_Avoid_: Telecast movement, teleport-cast — telecasting produces no movement of
its own, it rebuilds one that was already compiled.

**Teleport region**:
A maximal run of consecutive Steps carrying the teleport key alone — what a
`TELEPORT_*` component compiles to, and the unit a Telecast replaces. Its own
duration is the budget the replacement has to spend, so nothing outside the
compiled Input Sequence is needed to rebuild it.
_Avoid_: Teleport block, teleport chunk.

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

**Movement lab**:
The offline suite that compiles a fixed corpus of Movement Plans and checks the
Invariants and Expectations against them, with no game client involved. Green
means the Invariants hold, not that the bot works.
_Avoid_: Movement tests, movement framework — "framework" is the whole effort,
the lab is only its offline half.

**Fixture map**:
A small map config written by hand for the lab, built to force one movement type
rather than to describe a real place. Distinguished from the real mapfiles the
bot actually runs on, which the lab also uses but which cover only whatever
movements they happen to contain.
_Avoid_: Test map, fake map — the real mapfiles in the corpus are test maps too.

**Corpus**:
The maps the lab compiles against, plus the frozen sample of start-and-end pairs
per map. Fixed and checked in, so a failure is reproducible from a test id alone.
_Avoid_: Test data, dataset.

**Golden**:
The recorded compilation of one curated Movement Plan, checked in and compared
against on every run: the Holds it produces, then its Steps run-length collapsed.
Times are quantized, so a Golden pins structure and cadence and says nothing
about the per-Step jitter.
_Avoid_: Snapshot — the codebase already uses "snapshot" for a copy of bot data.

**Provenance**:
The record, carried alongside an Input Sequence, of which Movement Plan component
produced each Step. Not derivable from the Steps themselves; the compiler is the
only layer that knows the boundaries.
_Avoid_: Origin, source, mapping.
