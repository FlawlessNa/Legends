# Writing a DecisionMaker

How to write a new DecisionMaker, or port an old one, against the framework of ADR 0004: Data Keys, Providers and Pauses.
The terms are defined in `CONTEXT.md` ("Decision-making"); use them.

The framework is being built by epic #432.
What exists today: the Supervisor, Pauses, Data Keys, Providers and assembly.
What does not exist yet: Claims (`steers`), Signals (`announces`, `awaits`) and the crash policy.
No game Provider exists yet either; MapleStory's keys and Providers arrive with the first port.
Until then, an old-style DecisionMaker keeps its mixins, and the two kinds run side by side in one Bot.

## The shape

A DecisionMaker written against the framework:

- has no mixin in its class hierarchy (it may still subclass another DecisionMaker or a plain base class);
- declares the Data Keys it reads in `reads`, the ones it only peeks at in `observes`, and the classes it may pause in `pauses`;
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
- `steerable=True` marks a key a Claim may steer, once Claims exist.

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
- **Actions.** A Provider may send Actions with `self.send(request)` (the minimap's error handler moves the mouse).
  They carry no Correlation ID, since no single decision owns them, and `self.emit(...)` attributes the Provider's records to its own module.

## Reading data

- `self.read(KEY)` returns the key's value, typed, refreshed first when its threshold has passed.
  The key must be in `reads`, or it raises `KeyNotDeclared`.
- `self.peek(KEY)` returns the last known value without refreshing it, or None when there is none.
  The key must be in `reads` or `observes`.
  A key that is only observed never causes its Provider to be built, so `peek` is for a DecisionMaker that watches what others read, such as a state snapshot.
- A subclass that reads more than its parent writes `reads = (*Parent.reads, EXTRA)`.

## Assembly: what refuses the start

`Bot.start` assembles the Bot before the start barrier, before any DecisionMaker runs:

1. It collects the class-level declarations of every DecisionMaker; nothing is built yet.
2. It resolves the Providers of every key read, then of every key those Providers need, and orders them.
3. It refuses the start with `StartupRefused` on a cycle between Providers (naming it), two keys with the same name (naming both), or a `pauses` entry that resolves to nothing.
4. It builds every Provider, then runs each `setup()`, in order.
5. It builds every DecisionMaker, then runs each `setup()`.

So a Bot wired wrong fails at startup with a message that names the cause, never mid-session.

## Pausing other DecisionMakers

- Declare the classes you may pause: `pauses = (Rotation,)`.
  Where importing the class would create an import cycle, the entry is its dotted path as a string; assembly resolves it.
- Hold a Pause for as long as you need it: `async with self.pause(Rotation, reason="..."):`.
  It is released when the block exits, by any route, including your own decision being cancelled.
  Pass `cancel_actions=True` to also cancel the Actions the paused class already sent.
- A DecisionMaker that needs a human calls `self.pause_for_user(*classes, reason="...")`; only Discord `RESUME` releases it.
- A paused DecisionMaker keeps its state.
  Before every start and restart, the Supervisor calls `on_start()`, and once its loops have stopped, `on_stop()`: put resets there, never in an override of the loop.
- A DecisionMaker with several loops (one per buff) overrides `loops()`, and nothing else.

## Old and new side by side

- An unported DecisionMaker declares nothing and builds no Provider; it keeps doing its I/O in `__init__`, and its `setup()` stays empty.
- It reads a Provider's value as `data.<legacy_name>`, and every `BotData` method that takes a name (`get_last_known_value`, `update_attribute`, the time queries) accepts the legacy name too.
- `create_attribute`, `create_or_reconfigure_attribute` and `set_static` on a name a Provider owns raise `OwnedByProvider`: one producer per key.
- `_disable_decision_makers` and `_enable_decision_makers` remain as a shim for unported code only, with their old semantics.

## Testing one

A DecisionMaker's decisions can be tested without a game client:

- define the Providers and DecisionMakers the test needs in the test, and start a test Bot as `tests/test_botting/test_data_keys.py` does;
- give `BotData` a fake clock, `BotData(ign, clock=fake)`, so thresholds and the time queries move only when the test says, with no `sleep`;
- for Pauses, `tests/test_botting/test_supervisor.py` shows how to tell a running DecisionMaker from a paused one.

`docs/agents/testing.md` has the general rules.
