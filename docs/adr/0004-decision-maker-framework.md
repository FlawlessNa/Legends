---
status: accepted
---

# A decision-maker framework: a Supervisor, Pauses, Data Keys, Claims and Signals replace the mixins

## Context

DecisionMakers got their data and their capabilities from mixins.
A mixin registered string-keyed attributes on the Bot's shared `BotData`, bound to whichever DecisionMaker instance happened to create them, and set `has_*` flags that other code checked.
Nothing declared what a DecisionMaker needed, so a missing provider, a misspelled flag or two mixins writing the same attribute only showed up mid-session.

DecisionMakers paused each other ad hoc, and "pausing" meant three different things.
Each DecisionMaker started its own decide task plus two threads (an enabler and a disabler) blocking on Manager Conditions keyed by class name, which reached every bot in every Engine.
`Bot.pause()` and `Bot.resume()`, driven by Discord, found and recreated tasks by name prefix, and `RESUME` restarted DecisionMakers that had never been paused.
When a DecisionMaker died half-way through a pause or a steer, nothing undid it.

The intent and the approved spec are in epic #432.
This ADR records the decisions; the terms are defined in `CONTEXT.md` (Supervisor, Pause, Data Key, Provider, Claim, Signal).
The Supervisor and Pauses were delivered first (#433), then Data Keys, Providers and assembly (#434); what is named here but not yet in the tree is delivered by the later tickets of #432.

## Decision

### The Supervisor owns every decision loop

One `Supervisor` per Bot (`botting/core/supervisor.py`) runs every DecisionMaker's decision loops, old-style and new-style alike.
It is the only thing that cancels or restarts a loop.
It runs in the Engine's event loop: no thread, no Manager Condition and no `asyncio.to_thread` for pausing.

- A DecisionMaker with several loops (`SoloRebuff`, one per buff) declares them by overriding `loops()`, and nothing else.
- Before every start and restart of a DecisionMaker's loops, the Supervisor calls its `on_start()`.
  This replaced every `task()` override that reset state (Rotation's recovery grace period, MobsHitting's lock, `CheckMobsStillSpawn`'s timer).
- Once a DecisionMaker's loops have all stopped, by any route, the Supervisor calls its `on_stop()`.
  This replaced `TrialRunner`'s `task()` override, whose `finally` closed the Trial record; the spec did not name it, and a hook symmetric with `on_start()` was the smallest shape that keeps its behaviour with no `task()` left to override.
- A restart waits for every loop of the previous run to have ended, so two runs of one DecisionMaker never overlap.
- A loop that ends by itself, without a Pause, stays ended until the next Pause is taken and released, as a dead decision task always has.
- A loop that raises ends the Bot, as it always has; the crash policy is decided below and delivered by its own ticket.

### Pauses are scoped, stacking holds

A DecisionMaker pauses others by holding a Pause for as long as it needs: `async with self.pause(MobsHitting, reason=...)`.

- **Declared.** A DecisionMaker lists the classes it may pause in `pauses = (...)`.
  Where naming a class would create an import cycle, the entry is its dotted path, which assembly resolves; an entry that resolves to nothing refuses the start with `StartupRefused`.
  Pausing an undeclared class raises `PauseNotDeclared`.
  Pausing a class this Bot does not run is a no-op.
- **Exact class.** A Pause on `MobsHitting` does not pause `TelecastMobsHitting`, as the old class-name keys did not.
- **Effect.** A DecisionMaker going from no Pause to one has its loops cancelled at once; the object and its state are kept.
  When the last Pause is released, `on_start()` runs and its loops start again, each with a fresh decision and Correlation ID.
- **Stacking.** Any number of holders may pause the same DecisionMaker; it runs again only when every Pause is released.
- **Scoped.** A Pause is released when its block exits by any route: normal exit, an exception, or cancellation.
  A holder that is itself paused has its decision cancelled, so its block exits and its Pauses are released.
- **Not on itself.** A scoped Pause on the holder's own class is refused: it would cancel the block that holds it.
- **In-flight Actions.** By default a Pause sends nothing to Main Process and leaves an Action already sent alone, as the old disable did.
  `cancel_actions=True` also sends one request whose `cancel_tasks` names the paused classes' Actions through `action_name`.
- **The user.** Discord `PAUSE` is a Pause held by `"user"` on every DecisionMaker, plus the same movement-key release request it always sent.
  `RESUME` releases every user-held Pause, and every shim Pause.
  A DecisionMaker that needs a human takes a user-held Pause on the classes it names with `self.pause_for_user(*classes, reason=...)`; only `RESUME` releases it, and it may name its own class.
- **Address.** A Pause's target is a small value, `PauseTarget(bot, cls)`, resolved within this Bot, so a later cross-machine design can address another bot without changing call sites.
  Nothing addresses another bot yet.
- **Legacy shim.** `_disable_decision_makers(*names)` and `_enable_decision_makers(*names)` keep working for unported DecisionMakers, within this Bot only, with today's semantics exactly.
  A shim Pause is unscoped, is not released when its holder is paused, may be taken by a DecisionMaker on itself, and ends at the matching `_enable_decision_makers` call (whoever disabled it, as before) or at Discord `RESUME`.
  `self_only` is gone, since every pause is now per-bot (closes #52).
  The shim keeps emitting `decision.disabled` and `decision.enabled`, and is removed with the last mixin.
- **Telemetry.** `decision.paused` and `decision.resumed` carry the target, the holder and the reason, one pair per Pause.

### Naming another DecisionMaker's Actions

`action_name(cls, ign)` in `botting/core/` returns the identifier `cls`'s Actions carry for one bot, and `DecisionMaker.__repr__` is built from it, so the two cannot drift.
It is a plain function, so Main Process code (the Discord parser) uses it too.
A DecisionMaker lists the classes whose Actions it cancels in `cancels = (...)`.

A one-at-a-time gate replaces the hand-rolled per-DecisionMaker lock in Rotation and MobsHitting, keeping each one's exact use, with the Manager lock underneath because the release runs in Main Process.

### Data belongs to the Bot

- **Providers over mixins with declared strings (D9).**
  Declared strings would catch missing data at startup, but data would stay bound to the DecisionMaker instance that created it, which is the cause of the competing-setup bugs.
  Composition, each DecisionMaker owning its readers, loses sharing.
- **Values stay in `BotData`'s `ManagedAttribute`s.**
  A new store would duplicate thresholds, error handlers and history, and break `get_last_known_value` for unported code.
  Refresh-on-read stays: making reads inert was offered (D6) and not chosen.
- **Providers are configured from the Bot's profile, not from a DecisionMaker.**
  It is the only source that exists before any DecisionMaker is built, and it is single, so there is nothing to reconcile.
- **Provider Actions carry no Correlation ID.**
  Passing the reading decision's id would need ambient propagation, which the codebase rules out (ADR 0001: Correlation IDs are passed explicitly).
- **A key names its Provider, and the key fills the Provider's `provides`.**
  `Key(name, provider=..., legacy_name=..., steerable=...)` is defined after its Provider's class, and making it appends it to that class's `provides`; a Provider that declares `provides` itself is a `TypeError`.
  So a key has one producer by construction, and `provides` cannot drift from the keys.
  Rejected: a dotted-path `provider`, as `pauses` allows, which would leave the key untyped until assembly.
- **A key's value is stored under its `name`; `legacy_name` is an alias.**
  `data.<legacy_name>`, and every `BotData` method that takes a name, reach the key's attribute, so unported code reads and updates it unchanged, and dropping the alias with the last mixin moves nothing.
  `create_attribute`, `create_or_reconfigure_attribute` and `set_static` on a name a Provider owns raise `OwnedByProvider`; `set_static` too, since a static of that name would silently be shadowed.
  `reconfigure_attribute`, `snapshot_attribute` and `restore_attribute` still work on it, for the unported code that steers today, until Claims replace them.
- **Assembly is `Bot.start`, before the start barrier.**
  `resolve_providers` reads the class-level `reads`, `observes` and `needs` with nothing built, and refuses two keys of one name (a legacy name counts as a name) and any cycle between Providers, naming it.
  Every Provider is then built before any is set up, so a Provider that cannot even be built stops the start before any I/O; each `setup()` runs after those of the Providers it needs, and must register every key its class provides.
  The DecisionMakers are built after that, then each `setup()` runs; an old-style DecisionMaker's is empty.
- **A Provider takes the profile settings as keywords**, as a DecisionMaker does, so a Provider names the settings it uses in its signature.
- **`BotData` measures time on an injected monotonic clock** (#57, for `BotData` only).
  `AttributeMetadata`'s timestamps are readings of that clock, and "never" is minus infinity, so the time since an attribute that was never validly updated is infinite rather than the two thousand years `datetime.min` gave; every comparison against it is unchanged.
- **`StartupRefused` lives in `botting/core/`** (`errors.py`), and `maple/screen/sprites.py` raises that class.
  Two exception types for the same thing would make every caller catch both.
  It moved with the Supervisor, the first engine code to refuse a start, so that no step had two.

### Claims steer shared data

- **Claims are exclusive and refuse at once.**
  Waiting by default hides contention, and two takeovers waiting on each other would hang.

### Pausing, crashing and takeovers

- **A Pause cancels the decision in flight (D11).**
  Waiting for it to finish makes a pause take minutes to bite.
- **Pauses leave in-flight Actions alone by default.**
  That is the old behaviour, so porting changes no keys; the pauser opts in to cancelling them.
- **The legacy shim keeps today's semantics exactly**, including self-disabling and release by `RESUME`, so unported DecisionMakers behave as before.
- **A Pause covers its exact class only**, as before.
- **A crash stops the bot (D12).**
  An unattended bot must not run with its safety net gone.
  Per-DecisionMaker restart policies were offered and not chosen.
- **A takeover is an ordinary DecisionMaker (D13).**
  A first-class takeover unit would be designed for one parked user; it can be added on top of Pauses and Claims when the town trip is built.

### Signals, and the order of the work

- **Signals are built before their first user.**
  The cost is small, and a framework that lacks one makes the first user invent its own.
- **A Signal's waiters and latest announcement live on one board per Bot.**
  `wait_for` is a future per call on the Bot's event loop, resolved by `announce`, so every waiter wakes, and a cancelled wait (a Pause cancels a DecisionMaker's loops) leaves nothing behind.
  It waits for the next announcement only; a DecisionMaker that must not miss one reads `last` first.
  Rejected: a queue or event per waiter registered at assembly, which would make a Signal's waiters a thing to build and tear down.
- **`CheckStillInMap` is the first port, not `StateSnapshot` (a change from D14).**
  `StateSnapshot` only observes values others have read, so it moves last, once every key it observes has a Provider.
- **#57 is folded in only for `BotData`'s clock.**
  The `cooldown` decorator, movement recovery and the rebuff schedule keep their clocks; #57 stays open for them.
- **#49 (`disable_teleport` pops a class-level dict) stays standalone.**
  It is a bug in character data, outside the intent; the Rotation port keeps `disable_teleport`'s behaviour as it finds it.
- **`InventoryManager` stays parked and untouched**, even when the mixins it imports are removed: it already raises on import and is excluded from the gates.
- **The epic branch is cut from `dev`, and #302 is merged in by a ticket of its own.**
  The tickets that change only `botting/core` code #302 leaves alone start at once; the rest wait for that merge.
  Rejected: waiting for all of #302 before starting, which idles the core work; cutting from `epic/mscw-screen-reading`, where #397 and #399 keep changing the same mixins.

### One bot per machine, one Bot per Engine

Pauses, Claims and Signals are per-bot and in-process.
Cross-machine coordination will be a different mechanism, and only the Pause's address is shaped for it.

One bot per machine means **one Bot per Engine is assumed**.
A crash ends the Engine, and so ends only that bot.
A future Engine that runs several Bots must revisit this: ending the Engine would then end every Bot in it for one Bot's crash.

## Consequences

- No DecisionMaker starts a thread or waits on a Manager Condition to be paused, and `ProxyFactory.shared(..., "disabler"|"enabler", ...)` has no caller.
  An Engine now runs one task per DecisionMaker loop plus one Supervisor task per DecisionMaker, and no threads, where it used to run two blocked threads per DecisionMaker.
- The shim no longer reaches across Engines: `_disable_decision_makers("Rotation")` pauses this Bot's Rotation only.
  With one bot per machine nothing relied on the reach.
- `RESUME` no longer restarts a DecisionMaker that was never paused, and no longer starts a second loop beside a running one.
- A DecisionMaker that pauses itself through the shim stops at its loop's next `await`, as it did when the disabler thread cancelled it; the thread is simply gone from between.
- What a holder that is paused, cancelled or crashes leaves behind is nothing, by construction, for scoped Pauses; the shim keeps the old hazard until its last caller is ported.
