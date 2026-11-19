import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from .claims import Claim, ClaimHeld, Source
from .errors import StartupRefused

if TYPE_CHECKING:
    from .data_keys import Key, Provider, Providers

logger = logging.getLogger(__name__)

#: A monotonic clock, in seconds. Only differences between two of its readings
#: mean anything.
type Clock = Callable[[], float]

#: "Never" for the metadata timestamps: any reading of the clock is infinitely
#: long after it.
NEVER = float("-inf")
N_RET_VALUES = 10


@dataclass
class AttributeMetadata:
    """
    A data container instance used by ManagedAttribute to retain the overall frequency
    of updates for each attribute, as well as the average update time and the last
    N values of the attribute.
    """

    access_count: int = 0  # Number of times the attribute has been accessed
    update_count: int = 0  # Number of times the attribute has been updated
    total_update_time: float = 0.0  # Total time spent updating the attribute
    # When the attribute was last updated, last validly updated, and last changed,
    # on the owner's monotonic clock.
    last_update_time: float = NEVER
    last_valid_update_time: float = NEVER
    last_value_change_time: float = NEVER
    # Last N values of the attribute
    prev_values: deque[Any] = field(default_factory=lambda: deque(maxlen=N_RET_VALUES))

    @property
    def average_update_time(self) -> float:
        """
        Calculate the average update time for the attribute.
        :return: Average update time.
        """
        return self.total_update_time / self.update_count


class ManagedAttribute:
    """
    Encapsulates all state and behavior for a single managed attribute within
    BotData. Each ManagedAttribute holds the attribute's current value, its
    metadata, update function, refresh threshold, and optional error handler.

    This replaces the previous approach where per-attribute data was scattered
    across multiple parallel dictionaries in BotData.
    """

    def __init__(
        self,
        name: str,
        update_function: Callable[..., Any],
        threshold: float | None = None,
        initial_value: Any = None,
        error_handler: Callable[..., Any] | None = None,
        max_retries: int = 1,
        clock: Clock = time.monotonic,
        **metadata_kwargs: Any,
    ) -> None:
        """
        :param clock: What the threshold and the metadata's timestamps are
            measured on. The real monotonic clock unless a test injects its own.
        """
        self.name = name
        self.clock = clock
        self.value: Any = initial_value
        self.metadata = AttributeMetadata(**metadata_kwargs)
        self.update_function = update_function
        self.threshold = threshold
        self.error_handler = error_handler
        self.max_retries = max_retries

    def get(self, owner: BotData) -> Any:
        """
        Returns the current value, automatically refreshing if the threshold
        has been exceeded since the last update.
        """
        self.metadata.access_count += 1
        threshold = self.threshold or float("inf")
        if self.clock() - self.metadata.last_update_time > threshold:
            logger.debug("%s Updating %s due to exceeded threshold.", owner, self.name)
            self.update(owner)
        return self.value

    def set(self, value: Any) -> None:
        """
        Sets the value and appends it to the history of previous values.
        """
        self.value = value
        self.metadata.prev_values.append(value)

    def update(self, owner: BotData) -> None:
        """
        Refreshes the value by calling the update function. Tracks metadata
        such as update count, timing, validity, and value changes.
        Falls back to the error handler if the update function raises,
        up to max_retries attempts.
        """
        self._update_with_retry(owner, retries_left=self.max_retries)

    def _update_with_retry(self, owner: BotData, retries_left: int) -> None:
        try:
            self._execute_update()
        except Exception:
            if self.error_handler is not None and retries_left > 0:
                self.error_handler()
                logger.info("Finished error handling for %s.", self.name)
                self._update_with_retry(owner, retries_left - 1)
                logger.info("Successfully updated %s after error handling.", self.name)
            else:
                raise

    def _execute_update(self) -> None:
        """
        Calls the update function, updates metadata, and sets the new value.
        """
        started = self.clock()
        value = self.update_function()
        self.metadata.update_count += 1
        self.metadata.last_update_time = self.clock()

        if _update_is_valid(value):
            self.metadata.last_valid_update_time = self.metadata.last_update_time

        if _update_is_change(value, self.value):
            self.metadata.last_value_change_time = self.metadata.last_update_time
        self.set(value)
        self.metadata.total_update_time += self.clock() - started


def _update_is_valid(value: Any) -> bool:
    if isinstance(value, np.ndarray):
        return not (np.all(value == 0) or value.size == 0)
    else:
        return value not in [None, "", [], {}, set()]


def _update_is_change(value: Any, prev_value: Any) -> bool:
    if isinstance(value, np.ndarray):
        return not np.array_equal(value, prev_value)
    else:
        return value != prev_value


@dataclass(frozen=True)
class _Held:
    """A Claim held, and what its release puts back on its key's attribute."""

    claim: Claim
    update_function: Callable[..., Any]
    value: Any
    last_update_time: float


class OwnedByProvider(Exception):
    """
    Code created an attribute under a name a Provider owns: a Data Key's name.
    One producer per key: the Provider is it.
    """


class BotData:
    """
    A data container instance used by a Bot instance to enable communication
    between its DecisionMakers. This is achieved by the fact that each DecisionMaker
    assigned to a Bot instance has access to the same BotData instance.

    Attributes are stored in two tiers:
    - _managed: Live attributes with update functions, thresholds, and metadata tracking.
    - _static: Simple key-value pairs for config/constants (no update function).

    When a managed attribute is accessed, its threshold is checked and the value is
    automatically refreshed if enough time has passed since the last update.

    A Data Key's value is a managed attribute too, stored under the key's name and
    registered by its Provider through `provide`. A DecisionMaker reads it with
    `read` and `peek`, never by name.
    """

    #: The instance attributes `__setattr__` sets directly, not as data.
    _OWN = frozenset(
        {
            "ign",
            "_managed",
            "_static",
            "_clock",
            "_owned",
            "_claims",
            "providers",
        }
    )

    def __init__(self, ign: str, clock: Clock = time.monotonic) -> None:
        """
        :param clock: What every attribute's threshold, and the time queries, are
            measured on. The real monotonic clock unless a test injects its own.
        """
        self.ign = ign
        self._managed: dict[str, ManagedAttribute] = {}
        self._static: dict[str, Any] = {}
        self._clock = clock
        #: Every key's name a Provider registered, to the key and that Provider.
        self._owned: dict[str, tuple[Key[Any], Provider]] = {}
        #: Each claimed key's name, to its Claim and what its release puts back.
        self._claims: dict[str, _Held] = {}
        #: The Bot's Providers, attached by `Providers` when the Bot makes them.
        #: None for data no Bot has.
        self.providers: Providers | None = None

    def __str__(self) -> str:
        return f"BotData({self.ign})"

    @property
    def clock(self) -> Clock:
        """What this data's thresholds and time queries are measured on."""
        return self._clock

    def __getattr__(self, name: str) -> Any:
        """
        Returns the value of an attribute, checking _managed, then _static.
        """
        managed = self.__dict__.get("_managed")
        if managed is not None and name in managed:
            return managed[name].get(self)
        static = self.__dict__.get("_static")
        if static is not None and name in static:
            return static[name]
        raise AttributeError(f"{name} not found in {self}")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Sets the value of a managed or static attribute. For internal attributes
        (`_OWN`), falls through to normal attribute setting.
        :raises ClaimHeld: `name` is a claimed key's: its holder's source serves it.
        """
        if name in self._OWN:
            super().__setattr__(name, value)
            return
        if name in self._managed:
            self._refuse_claimed(name)
            self._managed[name].set(value)
        elif name in self._static:
            self._static[name] = value
        else:
            raise AttributeError(
                f"{name} not found in {self}. Use create_attribute() or set_static()."
            )

    def get_last_known_value(self, name: str, update: bool = True) -> Any:
        """
        Returns the last known (non-None) value of an attribute, if it exists.
        """
        if name in self._managed:
            last_known_update = next(
                (
                    value
                    for value in reversed(self._managed[name].metadata.prev_values)
                    if value not in [None, "", [], {}, ()]
                ),
                None,
            )
            if not update:
                return last_known_update
            return getattr(self, name) or last_known_update
        raise AttributeError(f"{name} not found in {self}")

    def get_time_since_last_valid_update(self, name: str) -> float:
        """
        Returns the time since the last valid update of an attribute, in seconds:
        infinite when it was never validly updated.
        """
        if name in self._managed:
            return self._clock() - self._managed[name].metadata.last_valid_update_time
        raise AttributeError(f"{name} not found in {self}")

    def get_time_since_last_value_change(self, name: str) -> float:
        """
        Returns the time since the last value change of an attribute, in seconds:
        infinite when it never changed.
        """
        if name in self._managed:
            return self._clock() - self._managed[name].metadata.last_value_change_time
        raise AttributeError(f"{name} not found in {self}")

    def check_if_values_have_changed(self, name: str) -> bool:
        """
        Checks in the last known value to see if there was any change.
        """
        if name in self._managed:
            prev_values = self._managed[name].metadata.prev_values
            return not all(val == prev_values[-1] or val is None for val in prev_values)
        raise AttributeError(f"{name} not found in {self}")

    def update_attributes(self, *names: str) -> None:
        """
        Updates the values of the specified attributes.
        """
        for name in names:
            self.update_attribute(name)

    def update_attribute(self, name: str) -> None:
        """
        Updates the value of an attribute using the update function mapped to it.
        """
        if name not in self._managed:
            raise AttributeError(f"{name} not found in {self}")
        self._managed[name].update(self)

    def set_static(self, name: str, value: Any) -> None:
        """
        Register or update a static attribute (no update function, no metadata).
        :raises OwnedByProvider: a Provider owns `name`.
        """
        self._refuse_owned(name)
        self._static[name] = value

    def create_attribute(
        self,
        name: str,
        update_function: Callable[..., Any],
        threshold: float | None = None,
        initial_value: Any = None,
        error_handler: Callable[..., Any] | None = None,
        max_retries: int = 1,
    ) -> None:
        """
        Creates a new managed attribute. Raises if the attribute already exists
        in _managed.
        :raises OwnedByProvider: a Provider owns `name`.
        """
        self._refuse_owned(name)
        if name in self._managed:
            raise AttributeError(f"{name} already exists in {self}.")
        self._static.pop(name, None)
        self._managed[name] = ManagedAttribute(
            name=name,
            update_function=update_function,
            threshold=threshold,
            initial_value=initial_value,
            error_handler=error_handler,
            max_retries=max_retries,
            clock=self._clock,
        )
        if initial_value is None:
            self.update_attribute(name)

    # --- Data Keys ------------------------------------------------------------------

    def provide(
        self,
        key: Key[Any],
        provider: Provider,
        update_function: Callable[[], Any],
        threshold: float | None = None,
        initial_value: Any = None,
        error_handler: Callable[[], Any] | None = None,
        max_retries: int = 1,
    ) -> None:
        """
        Register `key`'s value, produced by `provider`: a managed attribute under
        the key's name, with today's thresholds, error handler and history. Like
        `create_attribute`, it is refreshed at once when no initial value is given.

        Called through `Provider.register`, in the Provider's `setup()`.
        :raises ValueError: `provider` is not the key's Provider, or already
            registered it.
        :raises StartupRefused: the key's name is already taken by another
            attribute.
        """
        if type(provider) is not key.provider:
            raise ValueError(
                f"{provider} registered {key.name!r}, which "
                f"{key.provider.__name__} provides."
            )
        if self.is_provided(key):
            raise ValueError(f"{provider} registered {key.name!r} twice.")
        name = key.name
        if name in self._owned or name in self._managed or name in self._static:
            raise StartupRefused(
                f"{provider} registers {key!r}, but {self} already holds an "
                f"attribute named {name!r}: rename the key or the attribute."
            )
        self._managed[key.name] = ManagedAttribute(
            name=key.name,
            update_function=update_function,
            threshold=threshold,
            initial_value=initial_value,
            error_handler=error_handler,
            max_retries=max_retries,
            clock=self._clock,
        )
        self._owned[name] = (key, provider)
        if initial_value is None:
            self.update_attribute(key.name)

    def is_provided(self, key: Key[Any]) -> bool:
        """Whether `key`'s Provider has registered its value."""
        owner = self._owned.get(key.name)
        return owner is not None and owner[0] is key

    def read[T](self, key: Key[T]) -> T:
        """
        `key`'s value, refreshed first when its threshold has passed.
        :raises LookupError: no Provider has registered `key`, which assembly
            does for every key a DecisionMaker declares in `reads`.
        """
        self._refuse_unprovided(key)
        return self._managed[key.name].get(self)

    def refresh[T](self, key: Key[T]) -> T:
        """
        `key`'s value, read now whatever its threshold, as `update_attribute`
        reads an attribute.
        :raises LookupError: no Provider has registered `key`.
        """
        self._refuse_unprovided(key)
        self.update_attribute(key.name)
        return self.read(key)

    def peek[T](self, key: Key[T]) -> T | None:
        """
        `key`'s last known value, without refreshing it: the latest one that is
        not empty, or None when there is none, or when `key`'s Provider was not
        built.
        """
        if not self.is_provided(key):
            return None
        return self.get_last_known_value(key.name, update=False)

    def valid_age(self, key: Key[Any]) -> float:
        """
        Seconds since `key` was last refreshed to a valid value (not None, nor
        empty), on this data's clock, without refreshing it: infinite when it
        never was.
        :raises LookupError: no Provider has registered `key`.
        """
        self._refuse_unprovided(key)
        return self.get_time_since_last_valid_update(key.name)

    def store[T](self, key: Key[T], value: T) -> None:
        """
        Set `key`'s value without running its update. Called through
        `Provider.store`.
        :raises LookupError: no Provider has registered `key`.
        :raises ClaimHeld: `key` is claimed: its holder's source serves it.
        """
        self._refuse_unprovided(key)
        self._refuse_claimed(key.name)
        self._managed[key.name].set(value)

    # --- Claims -------------------------------------------------------------------

    def claim[T](
        self, key: Key[T], source: Source[T], *, holder: str, reason: str
    ) -> Claim:
        """
        Claim `key` for `holder`: until `release`, its value comes from `source`,
        refreshed now and then on the key's own threshold, with its Provider's
        error handler. `DecisionMaker.claim` is the scoped way to hold one.
        :raises ValueError: `key` is not steerable.
        :raises LookupError: no Provider has registered `key`.
        :raises ClaimHeld: another holder claims `key`, naming it and its reason.
        :raises Exception: whatever `source` raised on the first refresh; the
            key is not claimed then.
        """
        if not key.steerable:
            raise ValueError(f"{key!r} is not steerable: nothing may claim it.")
        self._refuse_unprovided(key)
        self._refuse_claimed(key.name)
        provider = self._owned[key.name][1]
        managed = self._managed[key.name]
        held = _Held(
            Claim(key, holder, reason),
            managed.update_function,
            managed.value,
            managed.metadata.last_update_time,
        )
        managed.update_function = lambda: source(provider)
        self._claims[key.name] = held
        try:
            managed.update(self)
        except BaseException:
            self._put_back(held)
            raise
        return held.claim

    def release(self, claim: Claim) -> bool:
        """
        End `claim`: its key serves its Provider's own value again, the one it
        served when the Claim was taken, refreshed on its threshold from its
        Provider's own update. Releasing twice does nothing.
        :return: Whether `claim` was held.
        """
        held = self._claims.get(claim.key.name)
        if held is None or held.claim is not claim:
            return False
        self._put_back(held)
        return True

    def claim_on(self, key: Key[Any]) -> Claim | None:
        """The Claim held on `key`, or None when nothing claims it."""
        held = self._claims.get(key.name)
        return None if held is None else held.claim

    def _put_back(self, held: _Held) -> None:
        """Undo `held`: the Provider's own update, value and time of last update."""
        managed = self._managed[held.claim.key.name]
        managed.update_function = held.update_function
        managed.set(held.value)
        managed.metadata.last_update_time = held.last_update_time
        del self._claims[held.claim.key.name]

    def _refuse_claimed(self, name: str) -> None:
        held = self._claims.get(name)
        if held is not None:
            raise ClaimHeld(f"{held.claim}: release it first.")

    def _refuse_unprovided(self, key: Key[Any]) -> None:
        if not self.is_provided(key):
            raise LookupError(
                f"{key!r} has no value in {self}: {key.provider.__name__} was not "
                "built. A key is provided once a DecisionMaker's reads declares it."
            )

    def _refuse_owned(self, name: str) -> None:
        owner = self._owned.get(name)
        if owner is not None:
            key, provider = owner
            raise OwnedByProvider(
                f"{name!r} in {self} is {key!r}, which {provider} provides: read it, "
                "do not create it."
            )
