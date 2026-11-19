# Writing a DecisionMaker

How to write a new DecisionMaker, or port an old one, against the framework of ADR 0004: Data Keys, Providers, Pauses, Claims and Signals.
The terms are defined in `CONTEXT.md` ("Decision-making"); use them.

The framework is being built by epic #432.
What exists today: the Supervisor, Pauses, Data Keys, Providers, Claims, Signals, assembly and the crash policy.
MapleStory's keys and Providers are in `maple/decision_makers/providers/`, one module per Provider; its package docstring lists them.
`CheckStillInMap` is the first DecisionMaker ported, and the worked example below; `MobsHitting`, `SoloRebuff`, the consumables, `ChatReplies`, `CheckMobsStillSpawn` and `TrialRunner` are ported too.
Until each is ported, an old-style DecisionMaker keeps its mixins, and the two kinds run side by side in one Bot.

## The shape

A DecisionMaker written against the framework:

- has no mixin in its class hierarchy (it may still subclass another DecisionMaker or a plain base class);
- declares the Data Keys it reads in `reads`, the ones it only peeks at in `observes`, the steerable ones it may claim in `steers`, the classes it may pause in `pauses`, and the classes whose Actions it cancels in `cancels`;
- does no I/O in `__init__`, and does its one-time I/O in `setup()`;
- uses no `has_*` flag, no `hasattr`, no `getattr(self.data, ...)`, and no task name built from a string;
- stays an asynchronous loop: `_decide()` runs one decision, and Actions go to Main Process through `self.send(...)`.

What a mixin did for data becomes a Provider.
What it did as plain logic (mob counting, the closest mob's direction) becomes functions, or a small helper class the DecisionMaker holds.

## A minimal example

```python
from typing import Any

from botting.core import DecisionMaker, Key, Provider


class MobCountProvider(Provider):
    """Produces MOB_COUNT for the whole Bot, however many DecisionMakers read it."""

    def __init__(self, *args: Any, mob_count_threshold: int = 3, **settings: object) -> None:
        super().__init__(*args, **settings)  # pure: no I/O here
        self.mob_count_threshold = mob_count_threshold

    def setup(self) -> None:
        # One-time I/O first, if any, then one register per key provided.
        self.register(MOB_COUNT, self._count, threshold=0.5)

    def _count(self) -> int:
        ...


MOB_COUNT: Key[int] = Key("mob_count", provider=MobCountProvider)


class Looter(DecisionMaker):
    reads = (MOB_COUNT,)
    pauses = (Rotation,)
    _throttle = 0.5

    async def _decide(self) -> None:
        if self.read(MOB_COUNT) == 0:
            async with self.pause(Rotation, reason="looting"):
                await self._loot()
```

Nothing wires `MobCountProvider` to `Looter`: declaring `MOB_COUNT` in `reads` is enough.
When the Bot starts, assembly builds `MobCountProvider` once, sets it up, and only then builds `Looter`.

## Data Keys

A Data Key, `Key[T]`, names one piece of shared data, its type, and the one Provider that produces it.

- Define a key right after its Provider's class, in the Provider's module.
  Making the key adds it to the Provider's `provides`; a Provider never declares `provides` itself, so a key cannot have two producers.
- Its `name` is unique within a Bot.
  Assembly refuses two keys of one name, legacy names included.
- `legacy_name` is the name unported code reads it by, as `data.<legacy_name>`.
  Give one when the key replaces an attribute a mixin used to create, so the old DecisionMakers keep reading it unchanged.
- `steerable=True` marks a key a Claim may steer (see "Steering shared data: Claims"). `DESTINATION` is one.

## Providers

A Provider produces the values of the keys that name it.
It belongs to the Bot, not to a DecisionMaker.

- **`__init__` only wires.**
  It receives the Bot's `BotData`, the pipe, the `ProxyFactory`, and the Bot's profile settings as keywords: the same settings every DecisionMaker of the Bot receives.
  Name the settings you use as keyword parameters and pass the rest on to `super().__init__`.
- **`setup()` does the one-time I/O**, then calls `self.register(KEY, update_function, threshold=..., error_handler=..., max_retries=...)` once for every key the Provider provides.
  `register` takes exactly what `BotData.create_attribute` takes, and behaves the same: the value is refreshed on read once `threshold` seconds have passed, the error handler runs and the update is retried when it raises, and it is read at once when no `initial_value` is given.
  A Provider that does not register every key it provides refuses the start.
- **`needs`** lists the keys of other Providers this one reads, with `self.read(KEY)`.
  Assembly sets those Providers up first.
  Reading a key not in `needs` raises `KeyNotDeclared`.
- **Its own keys.** `self.read(KEY)` and `self.refresh(KEY)` also take a key the Provider provides, once it is registered (the minimap's error handler refreshes the minimap's reading).
- **Setting its own keys.** `self.store(KEY, value)` sets a key it provides without running its update: for a Provider that decides two keys at once, or replaces its value outside a refresh (`DESTINATION`'s Abandon).
  It refuses a claimed key; `self.claimed(KEY)` says whether one is, so a Provider steers its own key only when nothing claims it.
- **Actions.** A Provider may send Actions with `self.send(request)` (the minimap's error handler moves the mouse).
  They carry no Correlation ID, since no single decision owns them, and `self.emit(...)` attributes the Provider's records to its own module.

### Bot-level Providers

Some data is not produced from the settings but found and checked by the Bot at start: the game window's handle, the map checked on the minimap, the screen readers built from the sprites every DecisionMaker's `screen_readers` declares.
A **Bot-level** Provider serves it.

- It sets `bot_level = True`, and takes what the Bot found as keyword arguments beside the settings: `ScreenReadersProvider(..., sprites=..., minimap=...)`.
- The Bot builds it in `child_init`, with `data.providers.add(ProviderClass, **values)`, which sets it up at once.
  Assembly never builds one: it skips those built, and refuses a Bot whose DecisionMakers read a key of one its Bot did not build.
- `Bot.child_init` builds the first, `WindowProvider`, which serves `HANDLE` (`botting.core`).
  `MapleBot.child_init` adds MapleStory's, in the order it always found them: the screen readers, the map, the character, the map's mobs, then the client's frame and chat keys.
- A key a Bot-level Provider serves is read like any other: declare it in `reads`.
- A value the Bot changes while it runs is a Bot-level key too: `RepliesProvider` serves `REPLIES_ON`, and `Bot.replies` switches it, which refreshes the key for every reader. Never a `BotData` static read by name.

## Reading data

- `self.read(KEY)` returns the key's value, typed, refreshed first when its threshold has passed.
  The key must be in `reads`, or it raises `KeyNotDeclared`.
- `self.refresh(KEY)` reads the value now, whatever its threshold: for a decision that must see the client as it is, such as a fresh `FRAME`.
  It is what `data.update_attribute(name)` followed by `data.<name>` was.
- `self.peek(KEY)` returns the last known value without refreshing it, or None when there is none.
  The key must be in `reads` or `observes`.
  A key that is only observed never causes its Provider to be built, so `peek` is for a DecisionMaker that watches what others read, such as a state snapshot.
- A subclass that reads more than its parent writes `reads = (*Parent.reads, EXTRA)`.

## Assembly: what refuses the start

`Bot.start` assembles the Bot before the start barrier, before any DecisionMaker runs:

1. It collects the class-level declarations of every DecisionMaker; nothing is built yet.
2. It resolves the Providers of every key read or steered, then of every key those Providers need, and orders them.
3. It refuses the start with `StartupRefused` on a cycle between Providers (naming it), two keys with the same name (naming both), a DecisionMaker steering a key that is not steerable (naming both), a `pauses` or `cancels` entry that resolves to nothing, a Signal awaited that nothing in the Bot announces (naming the Signal and the DecisionMaker), or a key read whose Bot-level Provider the Bot did not build (naming it).
4. It builds every Provider not built yet (the Bot-level ones were, by `child_init`), then runs each `setup()`, in order.
5. It builds every DecisionMaker, then runs each `setup()`.

`Bot.start` runs this as `Bot.assemble()`, then waits at the start barrier.
A test that needs a Bot's DecisionMakers built as the Engine builds them calls `assemble()`.

So a Bot wired wrong fails at startup with a message that names the cause, never mid-session.

## Pausing other DecisionMakers

- Declare the classes you may pause: `pauses = (Rotation,)`.
  Where importing the class would create an import cycle, the entry is its dotted path as a string; assembly resolves it.
- Hold a Pause for as long as you need it: `async with self.pause(Rotation, reason="..."):`.
  It is released when the block exits, by any route, including your own decision being cancelled.
  Pass `cancel_actions=True` to also cancel the Actions the paused class already sent.
- A DecisionMaker that needs a human calls `self.pause_for_user(*classes, reason="...")`; only Discord `RESUME` releases it.
  To stop every other DecisionMaker of the Bot, declare them all, as `ChatReplies.pauses` (`GM_STOPS`) does, with a test that the list covers the package: a Pause on a class the Bot does not run does nothing.
- A paused DecisionMaker keeps its state.
  Before every start and restart, the Supervisor calls `on_start()`, and once its loops have stopped, `on_stop()`: put resets there, never in an override of the loop.
- A DecisionMaker with several loops (one per buff) overrides `loops()`, and nothing else.

## Steering shared data: Claims

A key declared `steerable` serves either its Provider's own value or, while a DecisionMaker holds a **Claim** on it, the value source that DecisionMaker claimed it with.

```python
from botting.core import fixed

class Rebuffer(DecisionMaker):
    steers = (DESTINATION,)

    async def _decide(self) -> None:
        async with self.claim(DESTINATION, fixed(spot), reason="rebuff spot"):
            ...
```

- Declare the keys you may claim in `steers`. Assembly builds their Providers, and refuses the start when one is not steerable. A steered key may also be read.
- What is claimed is a **source**: a function given the key's Provider, called at every refresh while the Claim is held. `fixed(value)` serves one value, `following(read)` whatever `read()` returns now, and a Provider's module may offer more: `wander` steers `DESTINATION` into its random mode. The key keeps refreshing on its own threshold; taking the Claim refreshes it once.
- **Exclusive.** A second Claim on a held key raises `ClaimHeld` at once, naming the holder and its reason. A DecisionMaker that wants to wait does so itself.
- **Scoped.** It is released when the block exits, by any route: normally, an exception, a Pause on its holder or a crash. The key then serves its Provider's own value again: the one it served when the Claim was taken, refreshed on its threshold from its Provider's own update.
- A Claim that belongs to a whole run, not to one decision, goes in `holds_for_run()`: the Supervisor enters it after `on_start()` and leaves it once the loops have stopped, before `on_stop()`. `TrialRunner` claims `DESTINATION` there.
- `data.claimed` and `data.released` record each Claim, with its key, holder and reason.
- `snapshot_attribute`, `reconfigure_attribute` and `restore_attribute` are for unported code only, and refuse a claimed key.

`CheckMobsStillSpawn` is the worked takeover: when mobs stop spawning it holds a Pause on mob hitting and a Claim on `DESTINATION` with `wander` until they come back, so nothing is left paused or claimed if it is cancelled half-way. When they never come back, it takes a user-held Pause on everything it stops before its own blocks release.

## Cancelling another's Actions, and taking turns

- An Action names the Actions it cancels in `cancel_tasks`, each with `action_name(cls, ign)`, never a string built by hand: `cancel_tasks=[action_name(Rotation, self.data.ign)]`.
  Declare those classes in `cancels = (...)`, as `pauses` is declared; assembly refuses an entry that resolves to nothing.
- A DecisionMaker that must send one Action at a time holds a `TurnGate` (the Turn Gate, `CONTEXT.md`), made in `setup()` over its Manager lock: `TurnGate(self._proxies.instance(repr(self), "Lock"))`.
  `await gate.enter()` waits for its turn without blocking the event loop (`gate.try_enter()` takes it only when it is free), `gate.releaser` goes in the Action's `callbacks` so Main Process leaves the gate once the Action is done, `await gate.leave()` leaves it for a decision that sends nothing, and `on_start()` calls `gate.reset()`.
  `MobsHitting` is the example.

## Signals

A Signal, `Signal[T]`, announces that something happened, so that other DecisionMakers wait for it instead of polling.
It is typed by its payload, and in-process: no Manager object, no thread, and nothing is sent to Main Process.
A Signal is not a Telemetry Record.

```python
MOB_KILLED: Signal[int] = Signal("mob_killed")


class Hitter(DecisionMaker):
    announces = (MOB_KILLED,)

    async def _decide(self) -> None:
        ...
        self.announce(MOB_KILLED, mob_id)


class Looter(DecisionMaker):
    awaits = (MOB_KILLED,)

    async def _decide(self) -> None:
        mob_id = await self.wait_for(MOB_KILLED)
```

- Define a Signal once, in the module of whoever announces it; whoever awaits it imports it.
  It is compared by identity.
- `announces` is declared by a DecisionMaker or a Provider.
  `awaits` is declared by a DecisionMaker.
  A Provider may announce from `setup()` or from an update function.
- `self.announce(SIGNAL, payload)` wakes every waiter.
  It raises `SignalNotDeclared` when the Signal is not in `announces`.
- `await self.wait_for(SIGNAL)` returns the payload of the next announcement after the call.
  An announcement made before the call does not count, so a DecisionMaker that must not miss one reads `last` first, then waits.
  It raises `SignalNotDeclared` when the Signal is not in `awaits`.
  Cancelling the wait, which a Pause does, leaves nothing behind.
- `self.last(SIGNAL)` returns the latest announcement, whose `.payload` is the payload and `.at` is when it came on the Bot's clock, or None when it has not been announced.
  The Signal must be in `announces` or `awaits`.
- Assembly refuses the start when a DecisionMaker awaits a Signal that no DecisionMaker or Provider of the Bot announces.
  A Provider is only built when a DecisionMaker reads one of its keys, so a Provider whose only job is to announce must also provide a key that is read.

## Old and new side by side

- An unported DecisionMaker declares nothing; it keeps doing its I/O in `__init__`, and its `setup()` stays empty.
- It reads a Provider's value as `data.<legacy_name>`, or by the key's name when the key has no legacy one, and every `BotData` method that takes a name (`get_last_known_value`, `update_attribute`, the time queries) accepts the legacy name too.
- A mixin method that used to create data asks for its Provider instead: `_create_minimap_attributes` is `self.data.build_provider(MinimapProvider)`, which builds and sets it up, after what it needs, unless it is built.
  However many DecisionMakers ask, it is set up once.
- `create_attribute`, `create_or_reconfigure_attribute` and `set_static` on a name a Provider owns raise `OwnedByProvider`: one producer per key.
- `_disable_decision_makers` and `_enable_decision_makers` remain as a shim for unported code only, with their old semantics.
- `NextTargetMixin._set_fixed_target` remains for unported code only (the parked `InventoryManager`): an unscoped hijack of `DESTINATION` through `snapshot_attribute`. A ported DecisionMaker claims the key instead.
- The other way round, a ported DecisionMaker that needs data an unported one still makes reads it through a plain function beside that one's mixin, which the mixin uses too, and which goes with it: `TelecastMobsHitting` reads the rotation's Movement Plan with `planned_movements(data)` until Rotation's port gives it a Provider.
  It does not keep the mixin in its hierarchy for it.

## A worked example: porting `CheckStillInMap`

`CheckStillInMap` (`maple/decision_makers/ensure_still_in_map.py`) checks every 3 s that the minimap shows the bot's map, recovers the minimap once when it does not, and stops the bot when it still does not.
Before its port it was:

```python
class CheckStillInMap(MinimapAttributesMixin, ReactionsMixin, DecisionMaker):
    def __init__(self, metadata, data, pipe, **kwargs):
        super().__init__(metadata, data, pipe)
        if not self.data.has_minimap_attributes:
            self._create_minimap_attributes()  # I/O: shows the minimap
        self.map_name = map_title(self.data.world_map)

    async def _decide(self):
        ...
        self._minimap_pos_error_handler()  # the mixin's recovery
        ...
        self._disable_decision_makers(
            "Rotation", "CheckStillInMap", "CheckMobsStillSpawn", "MobsHitting"
        )
        self._react("advanced")  # the mixin's reactions
```

The port, step by step:

1. **List what it reads.**
   Every `self.data.<name>` becomes a key: `current_frame` is `FRAME`, `minimap_reader` is `MINIMAP_READER`, `world_map` is `WORLD_MAP`.
   Look through the mixin methods it calls too: the recovery read the handle, the minimap's box and its reading; the reactions read the frame, the handle and the chat keys.
2. **Move the data a mixin created into a Provider.**
   `_create_minimap_attributes` became `MinimapProvider`: the same setup I/O, the same keys in the same order, the same thresholds and error handler.
   Declaring one of its keys in `reads` is what builds it, so the `has_minimap_attributes` check goes.
3. **Turn the mixin's logic into a helper the DecisionMaker holds.**
   The recovery is `MinimapRecovery`, the reactions are `Reactions`.
   Each declares the keys it reads as `reads`, and the DecisionMaker spreads them into its own, so it reads nothing undeclared:

   ```python
   reads = (WORLD_MAP, *MinimapRecovery.reads, *Reactions.reads)
   ```

   A helper keeps what the mixin did, even what was shared: `Reactions.react` keeps the one 10 s cooldown every holder in the process shares, as `ReactionsMixin._react` had, and the mixin now reacts through a `Reactions` of its own.
4. **Replace the shim with a Pause.**
   It stopped four classes until a human looked, so it takes a user-held Pause on the same four, itself included: `self.pause_for_user(Rotation, CheckStillInMap, CheckMobsStillSpawn, MobsHitting, reason=...)`, declared in `pauses`.
   Its own class is a dotted path there, since a class cannot name itself in its own body.
   Only Discord `RESUME` releases it; the shim also ended at any DecisionMaker's `_enable_decision_makers`.
5. **Move the reads and the I/O out of `__init__`.**
   `__init__` builds the helpers; `setup()` reads `WORLD_MAP` for the map's name, and refuses the start when there is no minimap reader.
6. **Read what must be fresh with `refresh`.**
   `data.update_attribute("current_frame")` then `data.current_frame` is `self.refresh(FRAME)`.
7. **Rewrite its tests on the new API** (`tests/test_maple/test_minimap_consumers.py`).
   They build the Bot-level Providers as `MapleBot.child_init` builds them, with a client that shows the frame the test sets, so the check runs against real keys and no game client.

What it decides, its thresholds, the classes it pauses and the keys it sends are unchanged.

## Testing one

A DecisionMaker's decisions can be tested without a game client:

- define the Providers and DecisionMakers the test needs in the test, and start a test Bot as `tests/test_botting/test_data_keys.py` does;
- give `BotData` a fake clock, `BotData(ign, clock=fake)`, so thresholds and the time queries move only when the test says, with no `sleep`;
- for Pauses, `tests/test_botting/test_supervisor.py` shows how to tell a running DecisionMaker from a paused one.

`docs/agents/testing.md` has the general rules.
