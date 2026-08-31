---
status: accepted
---

# Logging architecture: dictConfig levels, subsystem handlers, and a JSONL telemetry stream

## Context

Before this decision, `botting/__init__.py` set up one root logger with a
single per-day `RotatingFileHandler` plus a console handler at INFO.
`LOG_LEVEL` module constants — 28 of them, across 16 live modules, reaching
43 `logger.log(LOG_LEVEL, msg)` call sites — conflated a message's
*severity* with whether it was *visible at all*: a level was raised to force
something onto the console and zeroed to keep something off it. Most of those
calls were decision-narrative content ("Suspected Not in map. Toggling
minimap.") wearing a severity level as a visibility switch. There was no
structured, machine-analyzable output — every diagnostic signal was a
free-text line, and a separate wayfinder map (movement-framework) needs a
structured telemetry stream to compare predicted vs. actual movement
outcomes.

## Decision

### Severity and visibility become two dials

- Replace the `LOG_LEVEL` constants with `logging.config.dictConfig`, defined
  as a Python dict in `botting/logging_config.py` — logger names are already
  hierarchical, so per-subsystem verbosity becomes config, not code.
- **Files capture everything at DEBUG; only the console is filtered.** A
  record's level states how severe its event is, and a
  [Console Threshold](../../CONTEXT.md) map — logger-name prefix to the level
  the console shows from, longest prefix wins — decides who sees it. The map
  is seeded empty with an INFO default, and `BOTTING_CONSOLE` layers over it
  per run. This is what let the constants be **deleted outright** rather than
  transcribed, and it dissolves `NOTSET`-as-a-mute as a concept.

### Text logs: four Log Buckets in a per-Session directory

- Split the text handlers into four [Log Buckets](../../CONTEXT.md) —
  `movement`, `inputs`, `decisions`, `other` — one file each, plus a combined
  `session.log` that preserves the cross-subsystem interleaving the split
  files cannot reconstruct.
- Write into a directory scoped to one [Session](../../CONTEXT.md),
  `logs/<YYYY-MM-DD_HH-MM-SS>/`, rather than one calendar day; prune to the
  20 most recent at Session *start*, so a Session that died without tidying
  up is cleaned by the next one.
- Route by **name filters on the handlers**, not `loggers[...].handlers`.
  `Engine` and `PeripheralsProcess` run in child processes, so nearly every
  interesting record travels `QueueHandler` -> `QueueListener` -> handlers
  and never touches this process's logger hierarchy — hierarchy-based routing
  would route almost nothing.

### A general-purpose Telemetry Record stream

- Introduce a [Telemetry Record](../../CONTEXT.md) stream (JSONL), not scoped
  to movement — movement is only the first [Producer](../../CONTEXT.md).
  Envelope: `{timestamp, correlation_id, logger_name, event_type, payload}`.
  Reuses the existing child-process `QueueHandler`/`QueueListener` transport
  and writes into the same per-Session directory as the text logs, as an
  unrotated, line-buffered `telemetry.jsonl`.
- **The envelope is serialised to a JSON string at emit time, in the
  producing process**, and attached to an ordinary `LogRecord`. That fixes
  the timestamp at the moment of the decision rather than whenever the
  listener drained the queue, makes the record picklable unconditionally —
  which reusing the queue transport demands, and which payloads full of
  numpy, `Box` and `partial` would otherwise break silently inside logging's
  own error handling — and leaves the sink with nothing to do but write a
  line.
- **Emission uses `logger.handle()`, not `logger.log()`**: capture is total,
  and a Telemetry Record must not be suppressible by whatever level a logger
  happens to carry. Its level describes the transport, not the event; leaving
  it suppressible would reintroduce exactly the severity/visibility
  conflation this ADR removes. Encoding never raises — unserialisable values
  render with `repr`, and a degraded-payload envelope covers the rest, since
  a record that still correlates beats no record.
- Telemetry and narrative are separated **in both directions**: the sink
  filters on the record's own marker rather than trusting its wiring, and
  `not_telemetry` goes on every text handler — a Telemetry Record carries an
  empty message and would otherwise contribute a blank line per event to
  `session.log` and the console.

### Correlation ID

- A `uuid4` [Correlation ID](../../CONTEXT.md) is minted by the base class
  once per `DecisionMaker._decide()` call and exposed as the public
  `self.correlation_id`. It is **stamped onto every `ActionRequest` at send
  time**, through a `DecisionMaker.send()` chokepoint, and closed over by
  `self.emit()`. No `contextvars` or other ambient propagation.
- It is **nullable**: a record with no originating decision (Session startup,
  listener lifecycle) carries none rather than a synthetic id that correlates
  nothing.
- Main Process procedures take **no `correlation_id` parameter**.
  `AsyncTaskManager` reads it off the request and emits the `action.*`
  lifecycle records itself — these are the records that close the chain,
  joining a decision made in an Engine to what Main Process did with it. A
  Producer needing to emit from *inside* its procedure bakes the id into its
  `partial`, which is already built inside `_decide()`.

### Event Types and payloads: convention, not validation

- The `event_type` taxonomy is governed by **convention**: a dotted
  `<area>.<event>` [Event Type](../../CONTEXT.md) in `snake_case`, and a
  per-event `TypedDict` payload, both declared per Producer.
  `emit_event()`'s signature stays permissive (`str`, `dict[str, Any]`)
  because a validating emitter could raise inside a Producer — the one thing
  this design rules out end to end.
- Constants and payload types live **one module per layer**:
  `botting/telemetry_events.py` for the engine's own areas, and
  `maple/telemetry_events.py` for the game's. `botting/` never imports
  `maple/`, so a single shared module would invert the dependency. Areas are
  an open set; they are deliberately **not** the four Log Buckets, which
  partition code for routing and carry a catch-all `other` that is dead
  weight as a grouping key.
- Payloads carry **JSON primitives only, converted at the call site** — an
  `int()` around anything a numpy pipeline produced, a `Box` decomposed into
  named fields rather than passed whole. The encoder does not learn numpy.

### Which call sites become Telemetry Records

- A line becomes a Telemetry Record when it reports a decision or its
  outcome, carries fields worth aggregating, and a human watching the console
  does not need it. It stays a text log when a human does — a fault, or state
  the operator supervises. The start of a failsafe is news; silent recovery
  from one is data.

### Out of scope

- Pre-existing hazards in movement code (`except Exception: breakpoint()`,
  `DEBUG=True`/`cv2.imshow`) belong to the movement-framework map.

## Consequences

- **Cross-map dependency**: this decision is the JSONL envelope/transport
  contract the movement-framework map's telemetry layer consumes. Changing
  the envelope shape later means coordinating with that map. The `movement`
  and `rotation` areas are reserved for it, and `MovementPayload`'s field
  list is that map's to decide.
- Migration touched every module carrying a `LOG_LEVEL` constant, split into
  a mechanical dictConfig sweep and a separate, judgment-heavy pass that
  moved narrative call sites to `emit_event()` and re-derived each remaining
  site's honest severity. Of the 43 call sites, 19 became Telemetry Records
  and 24 stayed text logs.
- **The console is quieter, and its content changed.** It loses the dispatch
  chatter, the inventory milestones, the rebuff coordination and the combat
  lines, and keeps warnings, errors, and the genuine lifecycle notices. The
  Console Threshold map stays empty because honest severities plus the INFO
  default already land each record correctly; an entry is needed only where
  an honest severity and the right console are in tension.
- **A Producer cannot silence a Telemetry Record.** Capture is total, so any
  per-call-site visibility flag is the conflation this ADR removes wearing a
  different hat — `ActionRequest.log` was retired for exactly that reason.
- `uuid4` Correlation IDs are opaque by design — the JSONL stream is meant
  for an offline analyzer, not manual eyeballing. A behaviour pursued across
  several consecutive `_decide()` calls is several Correlation IDs, stitched
  back together offline; that unit is an Attempt, and reconstructing it is
  the analyzer's job, not the runtime's.
