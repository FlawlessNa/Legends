# Engine architecture

Orientation for working inside `botting/`. Read this before exploring the
package — it answers "what runs where" without the tool calls.

Diagrams of everything below live in [docs/ARCHITECTURE.md](../ARCHITECTURE.md);
they add nothing this file doesn't state, so don't open them to answer a
question. The rules that a change can *violate* are in
[botting/AGENTS.md](../../botting/AGENTS.md) and the two ADRs.

## Four kinds of process

- **Main Process** — one asyncio loop. Owns the `asyncio.PriorityQueue`, the
  `AsyncTaskManager`, one listener task per Engine, the Discord listener, the
  proxy listener, a `QueueListener` thread for logs, the Held-Keys Ledger, and
  every keystroke that reaches a client.
- **Engine Process** — one per bot group, spawned by `SessionManager.launch()`.
  Runs `asyncio.run()` over its Bots. Each Bot owns a `BotData` and a set of
  `DecisionMaker`s, each of which is one asyncio task plus two threads (an
  enabler and a disabler waiting on shared Conditions).
- **Peripherals Process** — one. Screen recorder, Discord I/O (user → main),
  Discord relay (main → user), as three tasks in one loop.
- **Manager Process** — `multiprocessing.Manager()`. Holds the `metadata`
  DictProxy, the logging queue, and every cross-process Condition, Lock and
  Barrier.

Transport facts that constrain code:

- Each Engine has **one** duplex `Pipe`, shared by every Bot in it. A
  `DecisionMaker` writes to it through `self.pipe`, never directly — use
  `send()`.
- Pipe reads block. Both ends poll via `asyncio.to_thread(pipe.poll)`. Don't
  add a blocking read to an event loop.
- Engines **read** the game clients (screenshots, OCR). Main Process **writes**
  to them. An Engine that tries to send input raises.

## The action path

The hot loop, in order. Steps 1–2 run in an Engine, 3–8 in Main Process.

1. `DecisionMaker._decide()` runs one cycle. The base class mints a fresh
   Correlation ID per cycle; subclasses never assign it.
2. `DecisionMaker.send(request)` stamps that id onto the `ActionRequest` and
   writes it to the pipe. Stamping happens at send, not at construction,
   because some requests are built once and re-sent many times.
3. `Engine.listener` (a task in Main) receives it and `await queue.put(...)`.
4. `asyncio.PriorityQueue` — one for the whole Session, highest priority first.
5. `AsyncTaskManager` disposes of it: cancel-or-raise on a duplicate
   identifier, then the priority gate (schedule / requeue after 1s / drop and
   fire callbacks), then cancel the tasks the request names, then
   `asyncio.create_task(request.procedure(...))`.
6. The procedure runs in Main. For movement that is `compile_and_send`.
7. Inside the focus lock: read the Held-Keys Ledger for this handle → compile
   the Movement Plan into an Input Sequence → stream the Steps, recording each
   one to the ledger as it lands.
8. `SendInput` reaches the foreground window.

Consequences worth knowing before you touch any of it:

- An `ActionRequest` carries a Movement Plan plus compile inputs, **never** a
  compiled Input Sequence. Compiling before the focus lock reopens the race
  ADR 0002 closes.
- Because Steps are recorded after they land, the ledger describes the
  Delivered Prefix, not the Input Sequence, whenever a cancel truncates one.
- Cancellation inside `focused_inputs` releases held direction keys. Don't
  reintroduce per-Action cancel callbacks for this.

## The control plane

A Discord message is parsed once, in Main, by `BaseParser.parse_message()`, and
then goes one of two ways:

- **An `ActionRequest`** → the priority queue, joining the action path.
- **A command string** (`PAUSE --ign X`) → broadcast to every Engine pipe →
  `_poll_for_updates` matches on ign → `getattr(bot, action)()`.

`Bot.pause()` is the shape to copy when an Engine needs something done to a
client: cancel the local tasks, then send a high-priority `ActionRequest` back
to Main to do the part that requires input.

## Logging and telemetry

- Child processes log through a `QueueHandler` into the Manager's queue; a
  `QueueListener` thread in Main drains it into the parent logger's handlers.
  Main's own loggers reach those handlers directly.
- Handlers fan out three ways: the console (gated per logger by its Console
  Threshold), four Log Bucket files plus a combined `session.log` (gated by
  `not_telemetry`), and `telemetry.jsonl` (gated by `is_telemetry`).
- One Session, one directory. It is built in `SessionManager.__init__` before
  the `QueueListener` snapshots the handler list — attach a sink after that
  point and records from child processes reach nothing.

## Shared state

Synchronisation primitives can't be pickled to a child process. To get one, an
Engine writes `metadata[key] = (type_name, args, kwargs)`, notifies the
`proxy_request` Condition and waits; Main's `_monitor_proxy` finds the one key
not in `ignored_keys`, replaces it with a real proxy, and notifies back.

Use `ProxyFactory` rather than the raw protocol:

- `instance(owner, type)` — popped after creation. Per-bot locks and conditions.
- `shared(group, name, type)` — persists, auto-registered in `ignored_keys`.
  Keyed by `DecisionMaker` class name, which is what makes
  `_disable_decision_makers("Rotation")` reach every bot in every Engine.

Anything written into `metadata` that is *not* a pending proxy request must be
registered in `ignored_keys`, or `_monitor_proxy` will try to service it as one.
`MetadataNamespace` does this for shared dicts.

## File map

| Concern | File |
| --- | --- |
| Session setup, teardown, proxy monitor | `botting/core/session_manager.py` |
| Engine child loop + Main-side listener | `botting/core/engine.py` |
| Bot lifecycle, pause/resume | `botting/core/bot.py` |
| Decide cycle, Correlation IDs, enable/disable | `botting/core/decision_maker.py` |
| Priority, cancellation, `action.*` telemetry | `botting/core/async_task_manager.py` |
| `ActionRequest`, `ActionWithValidation` | `botting/core/action_data.py` |
| Managed attributes, update thresholds | `botting/core/bot_data.py` |
| Proxy protocol / namespaced metadata | `botting/core/proxy_factory.py`, `metadata.py` |
| Focus lock, ledger, `SendInput`, the guard | `botting/controller/inputs/` |
| Key binds, mouse, high-level input | `botting/controller/high_level.py` |
| Recorder + both Discord directions | `botting/core/peripherals_process.py`, `botting/communications/` |
| Buckets, thresholds, dictConfig | `botting/logging_config.py` |
| `emit_event`, the JSONL sink | `botting/telemetry.py`, `telemetry_events.py` |

## Traps

- **`botting/core/_old/`** is the pre-rewrite engine. Nothing live imports it.
  Don't read it for reference, don't extend it, don't import it. If a search
  hits it, discard the result.
- **Don't add a module-level `LOG_LEVEL`.** Per-subsystem verbosity is
  `dictConfig` data (ADR 0001).
- **Don't validate inside `emit_event()`.** Telemetry may never raise inside a
  Producer.
- **Don't import `maple` from `botting`.** There are no exceptions left; the
  last violation (`visuals/object_detection.py`) was removed by #85.
- **Correlation IDs are passed explicitly.** No `contextvars`, no ambient
  propagation.
