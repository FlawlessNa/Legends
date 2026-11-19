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
The Supervisor and Pauses were delivered first (#433), then Data Keys, Providers and assembly (#434), then MapleStory's first Providers and the first port, `CheckStillInMap` (#438), then `MobsHitting`, `TelecastMobsHitting` and the Turn Gate (#439), then the buffs, status bar, quick slots and chat Providers with the ports of `SoloRebuff`, the consumables and `ChatReplies` (#440), then Claims, `DESTINATION` and the ports of `CheckMobsStillSpawn` and `TrialRunner` (#441), then the pathing Provider and the port of `Rotation` (#442); what is named here but not yet in the tree is delivered by the later tickets of #432.

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
- **"Every other DecisionMaker of this bot" is a declared list** (#440).
  A GM's line makes `ChatReplies` take a user-held Pause on `GM_STOPS`, its `pauses`: every DecisionMaker class of `maple.decision_makers` but its own, since a Pause on a class the Bot does not run does nothing.
  A test fails when a DecisionMaker of the package is missing from it, so a new one is stopped too.
  `RESUME` is what gives training back, as for any user-held Pause, so `Bot.resume` no longer calls an `on_resume` hook on each DecisionMaker, and the Bot no longer publishes its DecisionMakers' names as a `BotData` static; both existed only for the GM stop (#489).
  Rejected: an "every other" entry in `pauses` that assembly resolves against the Bot's classes, which would change the core for one user; and the class names looked up at run time, which is what the spec rules out.
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

- **`cancels` is resolved at assembly, like `pauses`** (#439): an entry is a class or its dotted path, and one that resolves to nothing refuses the start.
  It is a declaration, not a check on each request: `cancel_tasks` is filled with `action_name`, and nothing compares the two at run time.
  The Discord parser, which holds no DecisionMaker, names the same classes with `action_name` too.
- **The gate is `TurnGate`, in `botting/core/turn_gate.py`** (#439), the Turn Gate of `CONTEXT.md`: the spec's `try_enter()`, `await enter()` and `releaser`, plus `await leave()`, for a decision that sends nothing (MobsHitting released from the Engine, through a thread, as before), and `reset()`, for `on_start()`.
  `releaser` is the Manager lock's own `release`, so what travels to Main Process in an Action's callbacks is what travelled before.
  A DecisionMaker makes its gate in `setup()`, since asking Main Process for the lock is I/O.
  Named `TurnGate`, not `Gate`, because the glossary's Delivery Gate is a different thing.
- **`leave_now()` leaves the gate without yielding** (#442), for Rotation, which released its lock in the decision itself when it had nothing to send: `await leave()` would give the event loop away through a thread hop first, which moves when the next decision can start.
  Rotation calls no `reset()` in `on_start()`, as its `task()` override never released the lock; MobsHitting's did.

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
- **What the Bot finds at start is served by Bot-level Providers, which the Bot builds in `child_init`** (#438).
  The spec has every Provider built by assembly from the profile settings, but what `MapleBot.child_init` builds is found and checked with what no Provider has: every DecisionMaker class's `screen_readers`, the profile as the Bot resolved it, and the map checked on the minimap, with its key presses.
  So a Provider with `bot_level = True` takes those values as keywords, and the Bot builds it with `Providers.add` at the point `child_init` always published them: their I/O keeps its order and its timing, both before the start barrier.
  Assembly skips a Provider already built, and refuses a Bot whose DecisionMakers read a key of a Bot-level Provider its Bot did not build, naming it, before anything is built.
  Rejected: moving the start checks into the Providers' `setup()`, which would pass the DecisionMaker classes and the resolved profile as settings, and move the map check's key presses into assembly for nothing.
- **The game window's handle is the engine's.**
  `HANDLE` and `WindowProvider` are in `botting/core/window.py`, built first by `Bot.child_init` with what `Bot.find_handle` found, because the generic Bot both finds the handle and reads it (`Bot.pause`).
  The spec put the handle with MapleStory's Bot-level Providers; `maple/decision_makers/providers` re-exports `HANDLE` so a port imports every key from one place.
- **The replies switch is the engine's, and a Bot-level key** (#440).
  `REPLIES_ON` and `RepliesProvider` are in `botting/core/replies.py`, built on by `Bot.child_init` after `WindowProvider`, because the generic Bot is what the Discord grammar's `REPLIES OFF|ON` and the takeover a `WRITE` implies reach (`Bot.replies`, `Bot.takeover`).
  `Bot.replies` switches the Provider, which refreshes its key, so a DecisionMaker that replies declares `REPLIES_ON` in `reads` and reads it; the key has no threshold and changes only when switched.
  It replaces the `replies_on` static, which `ChatReplies` read by name.
- **A Bot's Providers are one `Providers` object, attached to its `BotData`** as `data.providers`.
  `child_init` makes it, assembly builds into it, and `BotData.build_provider(cls)` asks it for a Provider unless it is built: that is how a mixin that used to create data (`_create_minimap_attributes`) asks for its Provider, as the spec says.
  `Bot.start` runs assembly as `Bot.assemble()`, so a test builds a Bot's DecisionMakers as the Engine does.
- **`refresh(KEY)` reads a key now, whatever its threshold**, on `BotData`, a DecisionMaker and a Provider.
  It is what `update_attribute(name)` then `data.<name>` was, which a decision that must see the client as it is (`CheckStillInMap`'s frame) needs.
  A Provider may also read and refresh the keys it provides, once registered.
- **A helper a DecisionMaker holds declares the keys it reads** (`MinimapRecovery.reads`, `Reactions.reads`), and its holder spreads them into its own `reads`, so a helper never reads a key its holder does not declare.
  A helper keeps what its mixin shared: `Reactions.react` keeps the one 10 s cooldown every reaction in the process shares, and `ReactionsMixin` reacts through a `Reactions` until the last mixin goes.
- **A ported DecisionMaker may read data an unported one still makes, through a plain function beside that one's mixin** (#439).
  `TelecastMobsHitting` fused its cast into the rotation's Movement Plan, which `MovementsMixin` planned until Rotation's port gave it a Provider.
  So it read the plan with `planned_movements(data)` and froze its compile with `movement_compiler(data, ...)`, functions in `_rotation_mixins.py` that `MovementsMixin` called too, rather than keep the mixin in its hierarchy.
  The spec's guide covered old reading new (`legacy_name`), not new reading old.
  Those functions went with #442: the telecast reads `MOVEMENTS` and compiles through `PathingProvider`.
- **What a mixin did as plain logic is functions** (#439): `MobsHittingMixin` is gone, and the mob counting, positions and closest-mob direction are `maple/decision_makers/mob_detection.py`, called by `MobsHitting`, the smart rotation and `CheckMobsStillSpawn` with the client's handle.
- **`BotData` measures time on an injected monotonic clock** (#57, for `BotData` only).
  `AttributeMetadata`'s timestamps are readings of that clock, and "never" is minus infinity, so the time since an attribute that was never validly updated is infinite rather than the two thousand years `datetime.min` gave; every comparison against it is unchanged.
- **`StartupRefused` lives in `botting/core/`** (`errors.py`), and `maple/screen/sprites.py` raises that class.
  Two exception types for the same thing would make every caller catch both.
  It moved with the Supervisor, the first engine code to refuse a start, so that no step had two.

### Claims steer shared data

- **Claims are exclusive and refuse at once.**
  Waiting by default hides contention, and two takeovers waiting on each other would hang.
- **A Claim lives where the key's value does** (#441).
  `BotData.claim` puts the claimed source in place of the key's update function, keeps its threshold and its Provider's error handler, and refreshes it once, so the Claim bites at once; `DecisionMaker.claim` is the scoped way to hold one, and emits `data.claimed` and `data.released`.
  `reconfigure_attribute`, `snapshot_attribute` and `Provider.store` refuse a claimed key, so the legacy steer and a Provider's own writes cannot undo a Claim behind its back.
- **A source is a function of the key's Provider**, `Source[T] = Callable[[Provider], T]`, called at every refresh while the Claim is held (#441).
  `fixed(value)` and `following(read)` ignore the Provider; `wander`, in `DESTINATION`'s module, steers it into its random mode, which is what `CheckMobsStillSpawn` claims.
  Rejected: a source with no argument, which leaves no way to claim one of the Provider's own modes short of handing DecisionMakers the Provider.
- **Released, a key serves its Provider's own value as it was when the Claim was taken** (#441).
  The release puts back the Provider's update function, the value, and the time of its last update, so a key with a threshold refreshes on it as if nothing had claimed it.
  The legacy `restore_attribute` put back only the update function and left the hijacked value: after `CheckMobsStillSpawn`'s wander, the rotation now heads back to the destination it had, where it used to go on to the last point it wandered to.
- **`steers` builds the Provider as `reads` does, and a steered key may be read** (#441): `TrialRunner` refreshes the destination it claims.
  Assembly refuses a DecisionMaker that steers a key not declared `steerable`, naming both, before anything is built.
- **A Claim for a whole run is held by `holds_for_run()`** (#441).
  `TrialRunner` claims `DESTINATION` for as long as its loop runs, which no `async with` in one decision can scope.
  So a DecisionMaker may return a context manager from `holds_for_run()`, which the Supervisor enters after `on_start()` and leaves once the loops have stopped, before `on_stop()`: it is released by a Pause, the Bot ending or a crash, and taken again at the restart, and failing to take it is a crash of that DecisionMaker.
  The spec did not name it; it is the hook symmetric with `on_start()`/`on_stop()` that keeps the Claim scoped.
  Rejected: a Claim per decision, which records a `data.claimed` and a `data.released` ten times a second; and an unscoped Claim released in `on_stop()`, which is the legacy hazard again.
- **`DESTINATION` is the first steerable key** (#441), legacy name `next_target`, with `DESTINATION_PLATFORM` (legacy `next_feature`), both served by `DestinationProvider` in `maple/decision_makers/providers/destination.py`.
  It holds the two modes `NextTargetMixin` had, random and smart, picked by the profile's `smart_rotation_enabled` and `mob_count_threshold`; the feature-cycle mode the spec names went with the hand-made maps (#398).
  It is built by assembly when a DecisionMaker steers it, and otherwise when the unported Rotation's mixin asks `BotData` for it, before any destination is drawn either way.
  `NextTargetMixin` keeps only that request and the legacy hijack the parked `InventoryManager` uses.
- **A Provider steers its own key only while nothing claims it.**
  `Provider.claimed(KEY)` says whether something does, and `Provider.store(KEY, value)` sets a key it provides without its update (a mode that decides `DESTINATION` and its platform at once, Abandon), refusing a claimed one.
- **Movement recovery's Abandon goes through the Provider** (#441): `DestinationProvider.abandon()` draws a new destination, and does nothing while `DESTINATION` is claimed, when recovery logs that it kept its target and sends no alert.
  Recovery reaches the Provider with `Providers.get(cls)`: for code that asks a Provider to act, beside serving its keys.
- **Arrival is recorded by the Provider**, so `movement.target_reached` carries no Correlation ID and is attributed to the Provider's module (in the movement Log Bucket), where it carried the deciding loop's, Rotation's or `CheckMobsStillSpawn`'s.
  Smart rotation's look at where the character is on screen reads `ON_SCREEN_POSITION` only when a Bot provides it (mob hitting does), outside `needs`: a calibration bot that builds `DestinationProvider` has no chat reader to find the character with.
- **The pathing is `PathingProvider`** (#442), in `maple/decision_makers/providers/pathing.py`: what `MovementsMixin._create_pathing_attributes` set up, as keys under the same names (`ACTION_DURATION`, `MOVEMENT_HANDLER`, `PATH`, `MOVEMENTS`, `ALWAYS_RELEASE_KEYS`), with the same thresholds, and the Path planned to `DESTINATION`.
  It is configured from the profile's `movements_duration` and `disable_teleport`, which `Rotation.__init__` took.
  #441's bridges went with it: the pathing module of plain reads beside the mixins (the position, the physics, the platforms a Path reaches), and `TrialRunner`'s `MovementPlanner`.
- **What a DecisionMaker asks of the pathing beside its keys is a method of the Provider**, reached as Abandon reaches `DestinationProvider`: `physics()`, `compiler(correlation_id, lead=...)`, which freezes a plan's compile inputs, and `configure(...)`, which a Trial batch's Knobs call to change the cap, the precision thresholds and whether Paths may teleport, and which makes the handler again.
  The compile is a method, not keys, because it leads the plan from the capture time of the frame the Path was planned from, which only the Provider knows; the telecast passes `lead=False`, as it passed no read time before.
- **`disable_teleport` takes the skill off when `PathingProvider` is set up**, before it makes its handler, where `Rotation.__init__` did it; it is still the class-level dict #49 is about.
  Every Provider is set up before any DecisionMaker is built, so it now happens before every DecisionMaker, and on any Bot that builds the pathing: `TrialRunner`'s too, which never had it.
- **The destination reads the pathing outside `needs`**: `PathingProvider` plans to `DESTINATION`, so `DestinationProvider` is set up first and cannot need its keys back.
  It asks for the platforms a Path reaches through a function of the pathing module, which answers None until the handler is registered, as smart rotation reads `ON_SCREEN_POSITION` only when it is provided.
  The function is imported where it is called, since the pathing module imports `DESTINATION`'s.
- **Movement recovery is `MovementRecovery`, a helper `Rotation` holds** (#442), in `maple/decision_makers/recovery.py`.
  It declares the keys it reads, and sends, emits and pauses through its holder; it takes the physics as a callable, so it knows nothing of the pathing.
  Escalate takes a user-held Pause, `pause_for_user`, on the classes the legacy disable named (`ESCALATION_TARGETS`, dotted paths in `Rotation.pauses`, since each imports `Rotation`), so only `RESUME` ends it, where any `_enable_decision_makers("Rotation")` ended the shim's (`AbilityPointDistributor`'s, for one); its records are `decision.paused`, no longer `decision.disabled`.
  Its rungs cancel their holder's Actions with `action_name(type(holder), ign)`, which names what `f"{self}"` named.
- **`MovementsMixin` stays for what plans to a target of its own**: the movement playground, and the parked `InventoryManager`, on Bots that never build `PathingProvider`, whose names it would otherwise collide with (`OwnedByProvider`). It goes with the last mixin.
- **A takeover that gives up stops for the user before it lets go.**
  `CheckMobsStillSpawn`, when mobs never come back, takes a user-held Pause on the classes the legacy disable left stopped, mob hitting included, before its own Pause on mob hitting and its Claim are released; the release then changes nothing until Discord `RESUME`.

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

### The town trip, against Pauses and Claims

The spec asks whether the town trip (door cast, map change, shop, return) can be written against Pauses and Claims without the legacy shim (#441).
This is its skeleton, from the stages of the parked `InventoryManager`; whether it holds is the maintainer's judgment, and what it leaves open is listed after it.

A `TownTrip` DecisionMaker checks the inventory on its own throttle, and declares `steers = (DESTINATION,)`, `cancels = (Rotation,)` and, in `pauses`, the classes the trip stops: mob hitting, Telecast, the rebuffs and the consumables, which `InventoryManager` disabled, and also `CheckMobsStillSpawn` and `CheckStillInMap`, which would take a town with no mobs and another map for a failure, and `Rotation`.
When the inventory is full, one decision runs the whole trip inside `asyncio.wait_for(..., TIME_LIMIT)` and one outer `async with self.pause(MobsHitting, TelecastMobsHitting, SoloRebuff, PetFood, MountFood, CheckMobsStillSpawn, CheckStillInMap, reason="town trip")`.
Rotation keeps running under it, and does the walking.

1. **Door spot.** `async with self.claim(DESTINATION, fixed(door_spot), reason="town trip: door")`, and the trip waits until `POSITION` is within reach of it; Rotation walks there as to any destination.
2. **Door cast.** Still holding the Claim, `async with self.pause(Rotation, cancel_actions=True, reason="casting door")`: Rotation's Action in flight is cancelled, the cast goes out under the trip's own Turn Gate, and nothing else moves the character.
3. **Map change.** Under the same Pause on Rotation, the trip walks into the door with an Action of its own and waits for the minimap to show the town.
4. **Shop.** In town, the Pause on Rotation is released and `DESTINATION` claimed with `fixed(npc_spot)`: Rotation walks to the shop. Then `Rotation` is paused again for the shop's clicks, the items are sold, and the shop is closed.
5. **Return.** The door spot is claimed in town, Rotation walks there, the door is entered under a Pause on Rotation, and the trip waits for the minimap to show the farming map again.

Each block exits as its stage ends, so the Claims and Pauses nest by stage, and once the outer block exits everything it stopped runs again.
A trip that is cancelled half-way (a Pause on it, Discord `PAUSE`) or crashes leaves nothing paused or claimed.
A trip that fails (it times out, or a stage raises) must not hand a bot standing in town back to its farming DecisionMakers: like `CheckMobsStillSpawn`'s give-up, it takes a user-held Pause on every class it declares before its blocks exit, so the bot waits for a human.
No step needs `_disable_decision_makers`, `snapshot_attribute` or `reconfigure_attribute`.

What the skeleton leaves open, for the ticket that builds the trip:

- **The map is fixed at start.** `MAP_ID`, `WORLD_MAP`, `POSITION_FUSION` and the mobs are Bot-level, found once by `MapleBot.child_init`. A trip changes map twice, so those keys must follow the map (a Provider that refreshes them when the minimap shows another map), or the town's be claimed for the stay.
- **The door is a temporary portal.** Rotation walks into the door only if the foothold graph has an edge for it while it stands. That belongs to `PathingProvider` (#442): a steerable key, or an operation on the Provider, that adds the portal for the trip.
- **The position through a door.** `InventoryManager` took the minimap's error handler off `POSITION` while the map changed, so that a minimap read mid-change did not trigger recovery. Under the framework that is a Claim on a steerable `POSITION`, or the Provider holding while the map changes; `POSITION` is not steerable today.
- **Keys released at the end of each Action.** It set `always_release_keys` for the trip; that is `ALWAYS_RELEASE_KEYS` now (#442), which the trip makes steerable.
- **Waiting for arrival** is a poll of `POSITION` in this skeleton; `DestinationProvider` could announce a Signal on arrival instead.

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
