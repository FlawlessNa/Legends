# `botting/` — the engine layer

Generic bot infrastructure: process orchestration, input control, logging and
telemetry transport. It knows nothing about MapleStory, and nothing here may
import from `maple/`. The one existing import
(`botting/visuals/object_detection.py` → `maple_ign_finder`) is a defect to be
removed, not a pattern to copy.

## Orientation

`docs/agents/engine-architecture.md` covers what runs where: the four kinds of
process, the action path from `_decide()` to `SendInput`, the control and
logging planes, the proxy handshake, and a concern-to-file map. Read it before
exploring the package — it answers most "where does this happen" questions
without a search. The diagrams in `docs/ARCHITECTURE.md` are for humans and
carry nothing extra.

## Input goes through Main Process

ADR 0002 is load-bearing for everything under `controller/`:

- **All keyboard input is sent from Main Process.** The input-sending functions
  raise when called anywhere else — the rule is a crash, not a convention.
- **The Held-Keys Ledger is the authority** on what is currently down. Live
  queries read the ledger; `GetAsyncKeyState` survives only at the two
  reconciliation points, session start and focus switch.
- **Movement compiles at dispatch, inside the focus-lock critical section.** An
  `ActionRequest` carries a Movement Plan plus compile inputs, never a compiled
  Input Sequence. Compiling before the lock re-opens the race the ADR closes.

## Logging and telemetry

ADR 0001:

- Per-subsystem verbosity is `dictConfig` data, not code. Don't reintroduce
  module-level `LOG_LEVEL` constants.
- `emit_event(correlation_id, event_type, payload, logger_name=None)` keeps a
  permissive `str` / `dict[str, Any]` signature on purpose: the engine must not
  enumerate the game layer's vocabulary, and a validating emitter could raise
  inside a Producer. **Telemetry may never raise inside the thing it observes.**
- Correlation IDs are passed explicitly. No `contextvars`, no ambient
  propagation.
- The engine's own Event Types live in `botting/telemetry_events.py`; it and
  `maple/telemetry_events.py` never import each other.

## Dead code

`botting/core/_old/` is the pre-rewrite engine, kept for reference only. Nothing
live imports it. Don't extend it, and don't import from it in new code.
