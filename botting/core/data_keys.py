"""
Data Keys and Providers: data that belongs to the Bot, not to a DecisionMaker.

A **Data Key** (`Key[T]`) names one piece of shared data and its type, and the one
Provider that produces it. A **Provider** produces the values of one or more keys.
It belongs to the Bot: assembly builds it once, however many DecisionMakers read
its keys, from the Bot's profile settings.

A Provider's values live in `BotData`'s managed attributes, so refresh-on-read,
thresholds, error handlers and the metadata history are the ones every attribute
has always had.

Assembly (`resolve_providers`, then `Providers.build`) runs in `Bot.start`, before
the start barrier: it resolves the Providers the DecisionMakers' declarations need,
refuses a Bot wired wrong with `StartupRefused`, then builds and sets them up in
order. A Bot-level Provider is built by its Bot instead, in `Bot.child_init`, from
what the Bot found at start (`Providers.add`).

ADR 0004 records the decisions this module implements; `docs/agents/decision-makers.md`
is the guide to writing against it.
"""

import multiprocessing.connection
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from botting.logging_config import producer_logger_name
from botting.telemetry import emit_event

from .errors import StartupRefused

if TYPE_CHECKING:
    from .action_data import ActionRequest
    from .bot_data import BotData
    from .claims import Claim
    from .decision_maker import DecisionMaker
    from .proxy_factory import ProxyFactory
    from .signals import Announcement, Signal, SignalBoard


class KeyNotDeclared(Exception):
    """
    A DecisionMaker read or peeked a key its `reads` or `observes` does not
    declare, or a Provider read one its `needs` does not.
    """


class Key[T]:
    """
    The name and type of one piece of data a Bot shares, and its Provider::

        POSITION: Key[Reading[VirtualPosition]] = Key("position", MinimapProvider)

    Defined after its Provider's class: making the key adds it to the Provider's
    `provides`, so a key has one producer by construction. Compared by identity.
    """

    def __init__(
        self,
        name: str,
        provider: type[Provider],
        *,
        steerable: bool = False,
    ) -> None:
        """
        :param name: What the key is called, in `BotData` and in messages. Unique
            within a Bot; assembly refuses two keys of one name.
        :param provider: The Provider class that produces the key's value.
        :param steerable: Whether a DecisionMaker may steer the value with a
            Claim, declaring the key in its `steers`; assembly refuses a
            DecisionMaker that steers a key which is not.
        """
        self.name = name
        self.provider = provider
        self.steerable = steerable
        provider._add(self)  # pyright: ignore[reportPrivateUsage] - the key is what fills provides

    def __repr__(self) -> str:
        return f"Key({self.name!r}, provider={self.provider.__name__})"


class Provider:
    """
    Produces the values of the keys that name it, for one Bot.

    - `provides` is filled by the keys that name this class; a class never
      declares it.
    - `needs` lists the keys of other Providers this one reads. Assembly builds
      and sets those up first.
    - `__init__` only wires: no I/O. It takes the Bot's profile settings as
      keywords, the same every DecisionMaker of the Bot receives, so a subclass
      names the settings it uses and passes the rest on.
    - `setup()` does the one-time I/O, then registers every key the Provider
      provides with `register`.

    A Provider may send Actions through `send`; they carry no Correlation ID,
    since no single decision owns them.

    A **Bot-level** Provider (`bot_level = True`) serves what its Bot found and
    checked at start, such as the game window's handle. Its Bot builds it in
    `child_init` with `Providers.add`, handing it those values as keywords;
    assembly never builds one.
    """

    #: The keys this Provider produces. Filled by `Key`, never declared.
    provides: ClassVar[tuple[Key[Any], ...]] = ()
    #: The keys of other Providers this one reads.
    needs: ClassVar[tuple[Key[Any], ...]] = ()
    #: The Signals this Provider announces, with `announce`.
    announces: ClassVar[tuple[Signal[Any], ...]] = ()
    #: Whether its Bot builds this Provider, in `child_init`, from what the Bot
    #: found at start. Assembly refuses a Bot whose DecisionMakers read a key of
    #: a Bot-level Provider its Bot did not build.
    bot_level: ClassVar[bool] = False

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        if "provides" in cls.__dict__:
            raise TypeError(
                f"{cls.__name__} declares provides: a Key names its Provider, and "
                "making the Key adds it to provides."
            )
        cls.provides = ()

    @classmethod
    def _add(cls, key: Key[Any]) -> None:
        cls.provides = (*cls.provides, key)

    def __init__(
        self,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        proxies: ProxyFactory,
        **settings: object,
    ) -> None:
        """
        :param data: The Bot's data, where this Provider's values live.
        :param pipe: The Engine's end of the pipe to Main Process, for Actions.
        :param proxies: The Bot's `ProxyFactory`, for Manager objects shared
            with Main Process.
        :param settings: The Bot's profile settings this class does not name.
        """
        self.data = data
        self.pipe = pipe
        self.proxies = proxies
        self.settings = settings
        #: Set by assembly before any `setup()`. None for a Provider built alone.
        self._signals: SignalBoard | None = None
        self._logger_name = producer_logger_name(type(self).__module__)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.data.ign})"

    def setup(self) -> None:
        """
        The one-time I/O, then `register` for every key this Provider provides.
        Called once by assembly, after every Provider this one needs is set up.
        """

    def register[T](
        self,
        key: Key[T],
        update_function: Callable[[], T],
        threshold: float | None = None,
        initial_value: T | None = None,
        error_handler: Callable[[], object] | None = None,
        max_retries: int = 1,
    ) -> None:
        """
        Register `key`'s value, exactly as `BotData.create_attribute` registers an
        attribute: refreshed on read once `threshold` seconds have passed, with
        `error_handler` run and the update retried up to `max_retries` times when
        it raises. Refreshed at once when no `initial_value` is given.
        :raises ValueError: this Provider does not provide `key`.
        """
        if key not in type(self).provides:
            raise ValueError(
                f"{self} registered {key.name!r}, which {type(self).__name__} "
                "does not provide."
            )
        self.data.provide(
            key,
            self,
            update_function,
            threshold=threshold,
            initial_value=initial_value,
            error_handler=error_handler,
            max_retries=max_retries,
        )

    def read[T](self, key: Key[T]) -> T:
        """
        The value of a key this Provider needs or provides, refreshed first when
        its threshold has passed.
        :raises KeyNotDeclared: `key` is in neither this class's `needs` nor its
            `provides`.
        """
        return self.data.read(self._declared(key, "read"))

    def refresh[T](self, key: Key[T]) -> T:
        """
        The value of a key this Provider needs or provides, read now, whatever
        its threshold.
        :raises KeyNotDeclared: `key` is in neither this class's `needs` nor its
            `provides`.
        """
        return self.data.refresh(self._declared(key, "refreshed"))

    def _declared[T](self, key: Key[T], verb: str) -> Key[T]:
        cls = type(self)
        if key not in cls.needs and key not in cls.provides:
            raise KeyNotDeclared(
                f"{self} {verb} {key.name!r}, which {cls.__name__}.needs does not "
                "declare."
            )
        return key

    def store[T](self, key: Key[T], value: T) -> None:
        """
        Set the value of a key this Provider provides, without running its
        update: for a Provider that decides two keys at once, or replaces its
        own value outside a refresh (`DESTINATION`'s Abandon).
        :raises KeyNotDeclared: this Provider does not provide `key`.
        :raises ClaimHeld: `key` is claimed: its holder's source serves it.
        """
        if key not in type(self).provides:
            raise KeyNotDeclared(
                f"{self} stored {key.name!r}, which {type(self).__name__} does "
                "not provide."
            )
        self.data.store(key, value)

    def claimed(self, key: Key[Any]) -> Claim | None:
        """
        The Claim held on a key this Provider provides, or None when its own
        value is served: what a Provider checks before steering the key itself
        (`DESTINATION`'s Abandon does nothing while it is claimed).
        :raises KeyNotDeclared: this Provider does not provide `key`.
        """
        if key not in type(self).provides:
            raise KeyNotDeclared(
                f"{self} asked whether {key.name!r} is claimed, which "
                f"{type(self).__name__} does not provide."
            )
        return self.data.claim_on(key)

    def announce[T](self, signal: Signal[T], payload: T) -> None:
        """
        Announce `signal`, waking every DecisionMaker waiting for it.
        :raises SignalNotDeclared: `signal` is not in this class's `announces`.
        """
        self._board().announce(signal, payload, by=self)

    def last[T](self, signal: Signal[T]) -> Announcement[T] | None:
        """
        The latest announcement of `signal`, or None.
        :raises SignalNotDeclared: `signal` is not in this class's `announces`.
        """
        return self._board().last(signal, by=self)

    def _board(self) -> SignalBoard:
        if self._signals is None:
            raise RuntimeError(
                f"{self} has no Signals: they exist only once its Bot has started."
            )
        return self._signals

    def send(self, request: ActionRequest) -> None:
        """Send an Action to Main Process. It carries no Correlation ID."""
        request.correlation_id = None
        self.pipe.send(request)

    def emit(self, event_type: str, payload: Mapping[str, Any] | None = None) -> None:
        """Emit a Telemetry Record, with no Correlation ID, from this module."""
        emit_event(None, event_type, payload, logger_name=self._logger_name)


# --- assembly -------------------------------------------------------------------------


def resolve_providers(
    classes: Iterable[type[DecisionMaker]],
) -> list[type[Provider]]:
    """
    The Providers `classes` need, in the order to build them: every Provider
    after the Providers it needs. Runs before any Provider or DecisionMaker is
    built, from the class-level declarations alone.

    A key in `reads` or `steers` has its Provider built, and so does every key
    that Provider needs, transitively. A key only in `observes` builds nothing.
    :raises StartupRefused: a DecisionMaker steers a key that is not steerable,
        naming both, two keys share a name, naming both, or the Providers form a
        cycle, naming it.
    """
    classes = list(classes)
    _refuse_unsteerable(classes)
    read = [key for cls in classes for key in (*cls.reads, *cls.steers)]
    observed = [key for cls in classes for key in cls.observes]

    reachable: dict[type[Provider], None] = {}
    pending = [key.provider for key in read]
    while pending:
        provider = pending.pop(0)
        if provider not in reachable:
            reachable[provider] = None
            pending.extend(key.provider for key in provider.needs)

    keys = [*read, *observed]
    for provider in reachable:
        keys += [*provider.provides, *provider.needs]
    _refuse_shared_names(keys)

    return _ordered([key.provider for key in read])


def _refuse_unsteerable(classes: Iterable[type[DecisionMaker]]) -> None:
    """Every key a DecisionMaker declares in `steers` is steerable."""
    for cls in classes:
        for key in cls.steers:
            if not key.steerable:
                raise StartupRefused(
                    f"{cls.__name__} steers {key!r}, which is not steerable: "
                    "declare the key steerable=True, or take it out of steers."
                )


def _refuse_shared_names(keys: Iterable[Key[Any]]) -> None:
    """Every key's name names that key only."""
    named: dict[str, Key[Any]] = {}
    for key in dict.fromkeys(keys):
        other = named.setdefault(key.name, key)
        if other is not key:
            raise StartupRefused(
                f"Two Data Keys share the name {key.name!r}: {other!r} and {key!r}. "
                "Rename one of them."
            )


def _ordered(roots: Sequence[type[Provider]]) -> list[type[Provider]]:
    """`roots` and every Provider they need, each after those it needs."""
    order: list[type[Provider]] = []
    done: set[type[Provider]] = set()
    #: The Providers being visited, each with the key that led to the next.
    path: list[tuple[type[Provider], Key[Any]]] = []

    def visit(provider: type[Provider]) -> None:
        if provider in done:
            return
        visiting = [p for p, _ in path]
        if provider in visiting:
            cycle = path[visiting.index(provider) :]
            raise StartupRefused(f"Providers form a cycle: {_describe(cycle)}.")
        for key in provider.needs:
            path.append((provider, key))
            visit(key.provider)
            path.pop()
        done.add(provider)
        order.append(provider)

    for root in roots:
        visit(root)
    return order


def _describe(cycle: Sequence[tuple[type[Provider], Key[Any]]]) -> str:
    """'A needs 'b' from B, which needs 'a' from A'."""
    steps = [f"needs {key.name!r} from {key.provider.__name__}" for _, key in cycle]
    return f"{cycle[0][0].__name__} " + ", which ".join(steps)


class Providers:
    """
    The Providers of one Bot: each built once, and set up after those it needs.

    `Bot.child_init` makes it and adds the Bot-level Providers (`add`); assembly
    builds the ones the DecisionMakers read (`build`); code outside assembly,
    such as a test, builds one on demand (`ensure`). However many ask, a
    Provider is built and set up once.

    Making it attaches it to `data`, as `data.providers`.
    """

    def __init__(
        self,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        proxies: ProxyFactory,
        settings: Mapping[str, object],
        signals: SignalBoard | None = None,
    ) -> None:
        """
        :param data: The Bot's data, where the Providers' values live.
        :param pipe: The Engine's end of the pipe to Main Process, for Actions.
        :param proxies: The Bot's `ProxyFactory`.
        :param settings: The Bot's profile settings: every Provider's keywords.
        :param signals: The Bot's Signals, for a Provider that announces one.
        """
        self.data = data
        self.pipe = pipe
        self.proxies = proxies
        self.settings = dict(settings)
        self.signals = signals
        #: Every Provider built, in the order they were built.
        self._built: dict[type[Provider], Provider] = {}
        data.providers = self

    def __iter__(self) -> Iterator[Provider]:
        """Every Provider built, in the order they were built and set up."""
        return iter(self._built.values())

    def __contains__(self, provider: type[Provider]) -> bool:
        return provider in self._built

    def get[P: Provider](self, provider: type[P]) -> P:
        """
        The `provider` this Bot built: for code that asks a Provider to do
        something beside serving its keys (movement recovery's Abandon asks
        `DESTINATION`'s Provider for another destination).
        :raises LookupError: this Bot did not build `provider`.
        """
        built = self._built.get(provider)
        if built is None:
            raise LookupError(f"{self.data.ign}'s Bot built no {provider.__name__}.")
        assert isinstance(built, provider), "built from the class it is kept under"
        return built

    def add(self, provider: type[Provider], **values: object) -> Provider:
        """
        Build the Bot-level `provider` with `values`, what its Bot found at
        start, and set it up now. Called by the Bot, in `child_init`.
        :param values: The keywords `provider` takes beside the profile
            settings; a value wins over a setting of the same name.
        :raises ValueError: `provider` is not Bot-level, is built already, or
            needs a Provider that is not built yet.
        """
        if not provider.bot_level:
            raise ValueError(
                f"{provider.__name__} is not Bot-level: assembly builds it, from "
                "the DecisionMakers' reads."
            )
        if provider in self:
            raise ValueError(f"{provider.__name__} is built already.")
        missing = [
            k.provider.__name__ for k in provider.needs if k.provider not in self
        ]
        if missing:
            raise ValueError(
                f"{provider.__name__} needs {', '.join(missing)}, which is not "
                "built yet: add it first."
            )
        built = self._make(provider, values)
        self._setup(built)
        return built

    def build(self, order: Sequence[type[Provider]]) -> None:
        """
        Build every Provider in `order` not built yet, then set each up, in
        `order`: every `__init__` runs before any `setup()`, so a Provider that
        cannot be built stops the start before any I/O.
        :raises StartupRefused: a Provider in `order` is Bot-level and its Bot
            did not build it, or a Provider's `setup()` did not register every
            key it provides.
        """
        pending = [cls for cls in dict.fromkeys(order) if cls not in self]
        unbuilt = [cls.__name__ for cls in pending if cls.bot_level]
        if unbuilt:
            raise StartupRefused(
                f"{', '.join(unbuilt)} is Bot-level, and {self.data.ign}'s Bot "
                "does not build it: a DecisionMaker that reads its keys runs only "
                "on a Bot that serves them."
            )
        built = [self._make(cls, {}) for cls in pending]
        for provider in built:
            self._setup(provider)

    def ensure(self, provider: type[Provider]) -> None:
        """Build and set up `provider`, after every Provider it needs, unless built."""
        self.build(_ordered([provider]))

    def _make(self, cls: type[Provider], values: Mapping[str, object]) -> Provider:
        provider = cls(
            self.data, self.pipe, self.proxies, **{**self.settings, **values}
        )
        provider._signals = self.signals  # pyright: ignore[reportPrivateUsage] - assembly wires it
        self._built[cls] = provider
        return provider

    def _setup(self, provider: Provider) -> None:
        provider.setup()
        missing = [
            key.name
            for key in type(provider).provides
            if not self.data.is_provided(key)
        ]
        if missing:
            raise StartupRefused(
                f"{provider}.setup() did not register "
                f"{', '.join(repr(name) for name in missing)}, which "
                f"{type(provider).__name__} provides."
            )
