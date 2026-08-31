# Load-bearing facts about today's engine

Extracted from `docs/ARCHITECTURE.md`, `docs/agents/engine-architecture.md`,
the ADRs, and the code, so a future session doesn't re-derive them. Verified
against the tree on 2026-08-30 (branch `share/onboarding`).

## The four processes, and which of them multi-machine touches

| Process | Multi-machine impact |
| --- | --- |
| **Main** — event loop, priority queue, Held-Keys Ledger, every keystroke | Gains one listener task (the Conductor client) alongside the existing Discord/proxy/engine listeners in `SessionManager.launch()`. Nothing else changes. |
| **Engine** — one per bot group; reads clients, never writes | Unchanged. Party state reaches DecisionMakers the same way commands do today: over the existing duplex pipe. |
| **Peripherals** — screen recording + both Discord directions | Discord's role shifts long-term (one console per *party*, not per session). Recording stays per-machine. |
| **Manager** — shared metadata, proxy handshake, cross-process primitives | Its *party-semantic* uses migrate behind a new interface; its intra-session uses (logging queue, per-bot locks, enable/disable Conditions) stay. |

## Exactly what crosses bot boundaries today

Inventory of cross-bot shared state (the only state a multi-machine layer must
carry over a network). Everything else in the engine is bot- or machine-local.

1. **Party rebuff coordination** — `maple/decision_makers/rebuffs.py`:
   - `_proxies.shared("PartyRebuff", "lock", "Lock")` and
     `("PartyRebuff", "event", "Event")` (lines 63–64).
   - Two shared dicts via `MetadataNamespace`: `character_locations` and
     `rebuffed` (lines 76–77 and throughout).
   - The logic is already a gather state machine: update own location →
     check max pairwise distance within threshold → set ready → cast → mark
     rebuffed, with a `_TIME_LIMIT` timeout. This shape survives a network
     almost unchanged; only the *arbitration* moves.
2. **DecisionMaker enable/disable gates** — `botting/core/decision_maker.py:47-48`:
   `shared(class_name, "disabler"/"enabler", "Condition")`. This is what makes
   `_disable_decision_makers("Rotation")` reach every bot in the Session — a
   *party-wide control* primitive in disguise.
3. **Launch Barrier** — `session_manager.py:138`: all bots start
   simultaneously. Cross-machine, this becomes a Conductor "start gate"
   rendezvous (or is simply dropped — open question).
4. **Discord control plane** — one Peripherals process parses commands for all
   bots in the session; command strings are broadcast to every Engine pipe.
5. Everything else in `_proxies.instance(...)` is **per-bot** (rotation lock,
   interface conditions, mob-spawn condition …) and stays machine-local.

## The seam that already exists

DecisionMakers never touch `multiprocessing` primitives directly for party
state — they go through `ProxyFactory.shared()` / `MetadataNamespace`
shared dicts. That indirection is where a coordination-backend abstraction
slots in without touching decision logic. (`botting/core/proxy_factory.py`,
`botting/core/metadata.py`.)

## The multi-client assumption, localized

Where "several clients share one keyboard" actually lives — i.e. what
"eventually retire" eventually deletes or degenerates:

- `botting/controller/inputs/shared_resources.py` — class-level
  `focus_lock`; `requires_focus` / `return_focus_to_owner` decorators; the
  `BlockInput` + `SetForegroundWindow` dance.
- `botting/controller/inputs/non_focused_inputs.py` — input path for
  non-foreground windows.
- Focus-switch reconciliation of the Held-Keys Ledger (ADR 0002): with one
  client, the only reconciliation point left is session start.
- ADR 0002's context section itself: both defects it fixes are *aggravated*
  by multi-client (foreground stealing, system-wide `GetAsyncKeyState`).
  Dispatch-time compilation stays correct and valuable with one client —
  preemption still truncates sequences — but the focus-switch half of the
  ledger machinery idles.
- Bot *grouping* (`SessionManager.launch(*grouped_bots)`, one Engine per
  group) exists to bundle same-machine clients. With one client per machine a
  Session degenerates to one group of one bot.

## Timing characteristics that matter for a network design

- The decide loop is throttled per DecisionMaker (`_throttle`, seconds-scale).
  Position reads come from minimap screenshots at similar cadence. Nothing in
  the party-coordination inventory operates faster than ~2 Hz.
- The only microsecond-sensitive region is inside the focus lock (compile +
  send Steps). **No network interaction may enter it.**
- Party rebuff already tolerates seconds of skew (characters path to a spot
  and wait). Internet latency between houses (tens of ms) is three orders of
  magnitude below the natural tolerance of every in-scope mechanic.

## Prior art in-repo worth imitating

- **"Priority is arbitrated in one place"** (`AsyncTaskManager`) — the design
  ethos to extend: party state arbitrated in one place.
- **`Bot.pause()` pattern** — cancel locally, then send a request for the part
  someone else owns. The same shape works for "Conductor asks a seat to do
  something": the seat's DecisionMakers translate it into local
  ActionRequests; the Conductor never reaches deeper.
- **Correlation ID** — already the tracing thread across process boundaries;
  extends across machine boundaries for free if party messages carry it.
- **The proxy handshake** — precedent for "ask for a primitive, receive a
  handle": the PartyServices interface (02) is its morally equivalent
  successor at party scope.
