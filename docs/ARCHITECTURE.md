# Engine architecture

How `botting/` works: four kinds of process, three planes of traffic between
them, and one rule that outranks the rest — **only Main Process may press a
key.**

This describes the generic engine only. `botting/` knows nothing about
MapleStory; `maple/` plugs into the seams described here. For the words used
below — Session, ActionRequest, Input Sequence, Held-Keys Ledger — see
[CONTEXT.md](../CONTEXT.md).

## Topology

A Session spawns three kinds of child process around Main Process, plus the
`multiprocessing.Manager` process holding everything they share.

![Process topology of the engine](img/engine-topology.svg)

| Process | How many | Owns |
| --- | --- | --- |
| **Main** | 1 | The event loop, the priority queue, the Held-Keys Ledger, and every keystroke that reaches a client |
| **Engine** | one per bot group | The Bots in that group, each with its own `BotData` and its own set of `DecisionMaker` tasks |
| **Peripherals** | 1 | Screen recording, and both directions of Discord traffic |
| **Manager** | 1 | The `metadata` dict, the logging queue, and every Condition, Lock and Barrier shared across processes |

Note the asymmetry at the top of the diagram: Engines **read** the game clients
(screenshots, pixel state, OCR), and Main Process **writes** to them. An Engine
never touches input.

Each Engine gets a single duplex `multiprocessing.Pipe`, shared by every Bot it
hosts. Reads on both ends block, so they sit on threads via
`asyncio.to_thread(pipe.poll)` rather than stalling their event loop.

Grouping is a launch-time decision: `SessionManager.launch()` takes groups of
Bots, runs each group in its own Engine, and treats the first Bot of the first
group as the Session's main bot.

## The action path

This is the loop the whole engine exists to run. A `DecisionMaker` never
presses anything — it describes what it wants and hands that description across
a process boundary. Everything past the boundary happens in Main Process, in
one event loop, arbitrated by priority.

![The path from a decision to a keystroke](img/engine-action-path.svg)

Three things are worth pulling out of the diagram.

**Compilation happens after the focus lock, not before it.** Held keys change
the *shape* of an Input Sequence — which keydowns get skipped, which delay is
used, which opposite keys get released — so compiling in the Engine at decide
time would build against a snapshot that is already stale by dispatch. An
`ActionRequest` therefore carries a Movement Plan plus the inputs needed to
compile it, never a compiled Input Sequence. This is
[ADR 0002](adr/0002-dispatch-time-compilation-held-keys-ledger.md).

**Priority is arbitrated in one place.** `AsyncTaskManager` is the only thing
that decides whether a request runs. A request that names a still-running task
with the same identifier either cancels it or raises; a request outranked by a
running blocker is either requeued after a delay or dropped with its callbacks
fired; everything else cancels the tasks it names and gets scheduled.

**The ledger describes what was delivered, not what was planned.** Steps are
recorded as they land, so when a higher-priority Action truncates a sequence
mid-flight the ledger matches the Delivered Prefix. Cancellation inside the
critical section also releases every direction key still held, which is why a
preempted movement never leaves the character walking.

## The control plane

Discord is the console. A message is parsed once in Main Process and then takes
one of two routes: something to *do* becomes an `ActionRequest` and joins the
action path above; something that changes what the bots *are* is broadcast to
every Engine as a plain command string.

![Discord control plane](img/engine-control-plane.svg)

Pausing is the clearest illustration of the input rule. An Engine can cancel its
own `DecisionMaker` tasks locally, but the movement keys those tasks left held
are Main Process' to release — so `Bot.pause()` cancels, then sends a
high-priority `ActionRequest` back the other way to drop the keys.

## The observability plane

Child processes don't own log files. They own a `QueueHandler` pointed at a
queue in the Manager process; a listener thread in Main drains it into the one
handler set that exists.

![Logging and telemetry](img/engine-logging.svg)

Two questions stay separate at the far end, which is the distinction
[ADR 0001](adr/0001-logging-architecture.md) exists to make:

- **Where does this record belong?** Its Log Bucket, derived from the logger
  name. A partition by area, never by severity.
- **Do I want to watch it right now?** Its Console Threshold, looked up per
  logger. Independent of what the files capture, which is always everything.

Text logs carry narrative — warnings, errors, lifecycle. Telemetry Records carry
the machine-readable "what did it decide, and why". They travel the same wires
and split at the last handler on a filter, which is why a record emitted deep in
an Engine lands in the same JSONL file as one emitted by the Task Manager in
Main.

Every record a decision caused carries that decision's Correlation ID —
including the ones Main Process emits once the resulting Action is dispatched.
That is what ties a decision to its consequences across the process boundary.

## Shared state: the proxy handshake

Synchronisation primitives can't be pickled across a pipe — a child process
can't just build a `Condition` that Main will honour. So an Engine *asks* for
one by writing a request into the shared metadata dict, and Main's Proxy
Listener builds the real object and writes it back.

![The proxy handshake](img/engine-proxy-handshake.svg)

The `ignored_keys` set is what makes step 3 unambiguous: every key that isn't a
pending request is registered there, so the listener finds the outstanding one
by elimination rather than by protocol tagging.

`ProxyFactory` wraps this in two namespaced calls. `instance()` proxies are
popped after creation — use them for per-bot locks. `shared()` proxies persist,
keyed by `DecisionMaker` class name, and are auto-registered in `ignored_keys` —
they're what makes `_disable_decision_makers("Rotation")` reach every bot in the
Session at once.

## Rules that crash, not conventions

Four properties hold everywhere above. Three of them are enforced in code —
break one and you get an exception, not a subtle bug six hours into a Session.

- **All keyboard input is sent from Main Process.** The input-sending functions
  call `require_main_process()` and raise anywhere else. `SendInput` only
  reaches the foreground window, and only Main arbitrates which client that is.
- **The Held-Keys Ledger is the authority on what is down.** Live queries read
  the ledger. `GetAsyncKeyState` survives at exactly two reconciliation points:
  Session start, and every focus switch.
- **Telemetry may never raise inside the thing it observes.** `emit_event()`
  keeps a permissive signature on purpose, and Event Types are governed by
  convention rather than validated at runtime.
- **Dependencies point one way: `maple` imports `botting`, never the reverse.**
  There are no exceptions — the last violation
  (`botting/visuals/object_detection.py`) was removed by #85.

## Where each piece lives

| In the diagrams | In the tree | Owns |
| --- | --- | --- |
| Session setup & teardown | `botting/core/session_manager.py` | Spawns everything, builds the log directory, waits on the listener set |
| Engine process + its listener | `botting/core/engine.py` | Both halves of the pipe: the child loop and the Main-side relay task |
| Bot · DecisionMaker | `botting/core/bot.py`, `decision_maker.py` | One client per Bot; the decide cycle, Correlation IDs, enable/disable gates |
| Priority queue & arbitration | `botting/core/async_task_manager.py` | Scheduling, requeueing, blocking, cancellation, `action.*` records |
| ActionRequest | `botting/core/action_data.py` | The wire format between an Engine and Main, plus the validated-retry wrapper |
| Ledger · focus lock · SendInput | `botting/controller/inputs/` | The critical section, the Main-Process guard, the per-Step ledger writes |
| Peripherals process | `botting/core/peripherals_process.py` | Recorder and both Discord directions, in one child loop |
| Buckets · thresholds · JSONL | `botting/logging_config.py`, `telemetry.py` | Routing by logger name, console visibility, the Telemetry Record sink |
| Proxy handshake | `botting/core/proxy_factory.py`, `metadata.py` | Namespaced requests and the `ignored_keys` bookkeeping |

## Deliberately not drawn

- `botting/core/_old/` — the pre-rewrite engine, kept for reference and imported
  by nothing.
- `botting/models_abstractions/` — the ABCs the game layer implements. No
  runtime role in the flows above.
- `botting/visuals/`, `botting/utilities/` — leaf helpers, called from inside the
  boxes rather than sitting between them.

---

The diagrams are hand-authored SVG in [img/](img/), theme-aware via
`prefers-color-scheme`. Edit the SVG source directly; there is no build step.
