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

## Movement calibration

**Trial**:
One closed-loop movement run under the real Session machinery — a start, a
target, a tolerance, and a time budget — recorded cycle-by-cycle for offline
analysis. The unit of movement calibration: judged on arrival reliability
first and time-to-arrival second, with oscillation and stuck events counted
as defects rather than averaged away.
_Avoid_: Run, experiment, test — a Session run, a measured experiment, and a
lab test are each different things here.

**Calibration constant**:
A value the movement system consumes that only the live game can settle,
supplied per stat-value (speed% / jump%) as session config. Starts from the
game-file physics derivations and is adjusted only when Trials demonstrate a
systematic bias — and then as a multiplier on the derivation, never as an
absolute minimap distance, so an adjustment fitted on one map ports to every
map's scale. Good enough for the loop to converge is the bar; exact is not a
goal.
_Avoid_: Physics constant — those are the fixed game-file source values a
calibration constant starts from.

**Knob**:
A controller parameter a Trial batch may override to sweep its effect — the
decision-loop interval, the Action duration cap, the narrow-platform and
edge-departure thresholds. Choosing new defaults from the measured curves is
calibration; redesigning the controller is a different effort.
_Avoid_: Setting, parameter — too generic to name the swept things.

**Trial schedule**:
The checked-in definition of one calibration experiment: a map, and the batches
of Trials to walk in order. Nested Schedule -> Batch -> Trial because a **Knob**
override is per batch, so a sweep is several batches over the same Trial list in
one reviewable file. Lives under `configs/trials/`; it is shared project data,
not per-user config.
_Avoid_: Campaign, suite, plan — a campaign is a sitting at the client, and
Movement Plan is already taken.

**Trial record**:
What a run of a Trial schedule leaves behind: per-machine JSONL, one line per
decision cycle and one per Trial outcome, under the gitignored `trial_records/`.
An experiment artifact, **not** Session telemetry — `telemetry.jsonl` describes a
Session and the logging map owns it. The two are joined on the Correlation ID a
cycle carries, never merged.
_Avoid_: Log, trace, telemetry — each names something the engine already owns.

## Movement attempts

**Precision movement**:
A Movement Plan transition whose success depends on the character being inside
a tight positional window when the gesture fires — jumping onto a rope, landing
on a narrow platform, jumping or teleporting from a platform's edge, entering a
portal, grabbing a ladder from a walk. A property of the transition (the
component, its upcoming component, and landing/departure flags), never of a
movement type alone: the same jump is precision onto a narrow perch and not
across open ground. The closed list of rows, with tiers and budgets, is the
precision-movement taxonomy (`docs/planning/`), cited by row id.
_Avoid_: Precise movement, tricky movement — the taxonomy's rows are the closed
list, not an impression.

**Attempt**:
One delivered gesture aimed at a single precision movement — one jump toward
the rope, one up-press at the portal — however many route cycles and
Correlation IDs it spanned. Reconstructed offline by the analyzer from position
history and telemetry, never delimited live. Consecutive Attempts at one
transition may be separated by unrelated recovery movement (the climb back
after a fall), so delimitation is "next gesture at the same transition", never
"next cycle".
_Avoid_: Try, retry — an Attempt includes the first try. Also avoid equating an
Attempt with a Correlation ID, whose span is one `_decide()` call.

**Attempt budget**:
The per-tier bound on how many Attempts one instance of a precision movement
may consume before that instance is judged failed — pass within the budget,
fail beyond it. An efficiency target and a humanization target at once:
repeated misses look bot-like, so a budget overrun is itself the signature
worth flagging. An Expectation reported by the offline analyzer, never a live
trigger — live reaction to the same symptoms belongs to Movement recovery.
_Avoid_: Retry limit, max attempts — the budget judges an instance offline; it
does not stop the bot mid-route.

## Movement recovery

**Stuck**:
The umbrella for the live symptoms of a rotation loop that has stopped
converging on its target — the failure family re-planning cannot fix, detected
symptom by symptom rather than diagnosed by cause. The symptoms are Stall,
Stagnation, Plan Churn, Target Timeout, and Starvation; each has its own
detector, and all feed one Reaction Ladder.
_Avoid_: Failsafe — that names the retired catch-all sentinel mechanism this
vocabulary replaces.

**Delivery Gate**:
The precondition behind which every Stuck detector accumulates: the rotation was
in control of the character during the window being judged. Time spent casting,
preempted, or waiting on arbitration counts toward no Stuck threshold — a
character that is not trying to move cannot be stuck. Control is read off
delivery — movement Steps actually sent to the game — with one exception: a
rotation that could produce no Movement Plan at all delivers nothing and is
nonetheless entirely on its own time, so the gate opens for it. That is the case
Starvation does not cover and the retired sentinels did.
_Avoid_: Attempt gate — an Attempt is the analyzer's offline unit, and this
gate is live.

**Stall**:
The Stuck symptom where movement was delivered yet displacement stayed within
detection jitter over the window. The fast special case of Stagnation: walls,
latched keys, a missed rope grab landing back on the same spot.
_Avoid_: Static position, not moving — raw coordinate equality is exactly the
detection this term replaces, defeated by knockback jitter.

**Stagnation**:
The Stuck symptom where the character moves but the remaining Path length stops
shrinking over the window. Measured on the freshly recomputed Path, never on
distance-to-target, so a legitimate detour away from the target is not
Stagnation by construction.
_Avoid_: No-progress — two words, and "progress" invites the distance-to-target
reading this term exists to rule out.

**Plan Churn**:
The Stuck symptom where the same quantized start and Movement Plan keep being
re-derived for one target without the remaining Path shrinking — the live
signature of oscillation and of feasibility errors that re-planning amplifies
instead of fixing.
_Avoid_: Oscillation — that is the Trial record's offline defect counter; Plan
Churn is the live detector whose firings the counter should corroborate.

**Target Timeout**:
The Stuck symptom where one target has not been reached within a budget derived
from its initial Path length, regardless of apparent motion. The backstop that
holds even when every finer detector is blind.
_Avoid_: Unreachable — reachability is the pathfinder's word for a grid
property; this is a live budget expiring.

**Starvation**:
The Stuck symptom where the rotation keeps producing movements but no movement
Step is delivered at all over the window — the loop starved by arbitration, not
blocked by terrain. Observed and reported only; it triggers no in-game
reaction, because nothing about the map is wrong.
_Avoid_: Deadlock, lock contention — those are causes; Starvation names the
observable symptom whatever the cause.

**Reaction Ladder**:
The single per-target escalation every Stuck symptom advances: Reflex (release
held keys, random jump), then Abandon (drop the target and alert), then
Escalate (pause the bot and alert, awaiting human resume). One ladder per
target — cascading symptoms of one incident advance it once — and real progress
resets it entirely.
_Avoid_: Failsafe response, escalation policy — the ladder is the mechanism's
name, its rungs are Reflex, Abandon, Escalate.
