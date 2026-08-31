---
status: proposed
---

# Logging architecture: dictConfig levels, subsystem handlers, and a JSONL telemetry stream

## Context

Today, `botting/__init__.py` sets up one root logger with a single
per-day `RotatingFileHandler` plus a console handler at INFO. Per-module
`LOG_LEVEL` constants, scattered across 28 files, are passed directly to
`logger.log(LOG_LEVEL, msg)` call sites — this conflates a message's
*severity* with whether it's *visible at all*, and most of these calls
are actually decision-narrative content ("Suspected Not in map. Toggling
minimap.") wearing a severity level as a visibility switch. There is no
structured, machine-analyzable output — every diagnostic signal is a
free-text line, and a separate wayfinder map (movement-framework) needs a
structured telemetry stream to compare predicted vs. actual movement
outcomes.

## Decision

- Replace the 28 `LOG_LEVEL` constants with `logging.config.dictConfig`,
  defined as a Python dict in a config module — logger names are already
  hierarchical, so per-subsystem verbosity becomes config, not code.
- Split text-log handlers by subsystem (movement/pathing, decisions/engine,
  catch-all), writing into a directory scoped to one [Session](../../CONTEXT.md)
  rather than one calendar day.
- Introduce a general-purpose [Telemetry Record](../../CONTEXT.md) stream
  (JSONL), not scoped to movement — movement is only the first
  [Producer](../../CONTEXT.md). Envelope: `{timestamp, correlation_id,
  logger_name, event_type, payload}`. `correlation_id` is a `uuid4`
  generated once per triggering `DecisionMaker._decide()` call and passed
  explicitly to `emit_event(correlation_id, event_type, payload,
  logger_name=None)` — no `contextvars` or other ambient propagation;
  each Producer decides how it threads the id through its own call stack.
  Reuses the existing child-process `QueueHandler`/`Queue` transport and
  writes into the same per-Session directory as the text logs.
- The `event_type` taxonomy is governed by **convention, not validation**: a
  dotted `<area>.<event>` [Event Type](../../CONTEXT.md) and a per-event
  `TypedDict` payload, both declared per Producer — for the game layer, in
  `maple/telemetry_events.py`. `emit_event()`'s signature stays permissive
  (`str`, `dict[str, Any]`) because `botting/` must not enumerate `maple/`'s
  vocabulary, and because a validating emitter could raise inside a Producer.
  Payloads carry JSON primitives only, converted at the call site.
- Pre-existing hazards in movement code (`except Exception: breakpoint()`,
  `DEBUG=True`/`cv2.imshow`) are out of scope — that code belongs to the
  movement-framework map.

## Consequences

- **Cross-map dependency**: this decision is the JSONL envelope/transport
  contract the movement-framework map's telemetry layer consumes. Changing
  the envelope shape later means coordinating with that map.
- Migration touches all 28 files carrying a `LOG_LEVEL` constant; split into
  a mechanical dictConfig sweep and a separate, judgment-heavy pass that
  moves narrative call sites to `emit_event()`.
- `uuid4` correlation ids are opaque by design — the JSONL stream is meant
  for an offline analyzer, not manual eyeballing.
