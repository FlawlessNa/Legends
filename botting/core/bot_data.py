import enum
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from .errors import StartupRefused

if TYPE_CHECKING:
    from .data_keys import Key, Provider

logger = logging.getLogger(__name__)

#: A monotonic clock, in seconds. Only differences between two of its readings
#: mean anything.
type Clock = Callable[[], float]

#: "Never" for the metadata timestamps: any reading of the clock is infinitely
#: long after it.
NEVER = float("-inf")
N_RET_VALUES = 10


class _Unset(enum.Enum):
    """
    "Argument not supplied", distinct from an explicit `None`.

    An `enum` member rather than a bare `object()` so that `is not _SENTINEL`
    actually narrows the parameter to its real type.
    """

    TOKEN = enum.auto()


_SENTINEL = _Unset.TOKEN


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
        self._snapshot: dict[str, Any] | None = None

    def snapshot_config(self) -> None:
        """
        Records the current update configuration so it can be put back later.

        Idempotent: a second call while a snapshot is already held is a no-op, so
        successive hijacks of the same attribute all restore to the configuration
        that was in place before the first one.
        """
        if self._snapshot is None:
            self._snapshot = {
                "update_function": self.update_function,
                "threshold": self.threshold,
                "error_handler": self.error_handler,
                "max_retries": self.max_retries,
            }

    def restore_config(self) -> None:
        """
        Puts back the configuration captured by snapshot_config() and drops the
        snapshot. No-op when nothing was snapshotted. The value and the metadata
        history are left untouched - only the update configuration is restored.
        """
        if self._snapshot is None:
            return
        self.update_function = self._snapshot["update_function"]
        self.threshold = self._snapshot["threshold"]
        self.error_handler = self._snapshot["error_handler"]
        self.max_retries = self._snapshot["max_retries"]
        self._snapshot = None

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


class OwnedByProvider(Exception):
    """
    Unported code created an attribute under a name a Provider owns: a Data Key's
    name, or its `legacy_name`. One producer per key: the Provider is it.
    """


class BotData:
    """
    A data container instance used by a Bot instance to enable communication
    between its DecisionMakers. This is achieved by the fact that each DecisionMaker
    assigned to a Bot instance has access to the same BotData instance.

    Attributes are stored in three tiers:
    - _managed: Live attributes with update functions, thresholds, and metadata tracking.
    - _static: Simple key-value pairs for config/constants (no update function).
    - _features: A set of feature flags (has_* convention).

    When a managed attribute is accessed, its threshold is checked and the value is
    automatically refreshed if enough time has passed since the last update.

    A Data Key's value is a managed attribute too, stored under the key's name and
    registered by its Provider through `provide`. New-style code reads it with
    `read` and `peek`; unported code reads it as `data.<legacy_name>`, and every
    method here that takes a name accepts the legacy name for the key's.
    """

    #: The instance attributes `__setattr__` sets directly, not as data.
    _OWN = frozenset({"ign", "_managed", "_static", "_features", "_clock", "_owned"})

    def __init__(self, ign: str, clock: Clock = time.monotonic) -> None:
        """
        :param clock: What every attribute's threshold, and the time queries, are
            measured on. The real monotonic clock unless a test injects its own.
        """
        self.ign = ign
        self._managed: dict[str, ManagedAttribute] = {}
        self._static: dict[str, Any] = {}
        self._features: set[str] = set()
        self._clock = clock
        #: Every name a Provider owns, the key's own and its legacy one, to the
        #: key and the Provider that registered it.
        self._owned: dict[str, tuple[Key[Any], Provider]] = {}

    def __str__(self) -> str:
        return f"BotData({self.ign})"

    def __getattr__(self, name: str) -> Any:
        """
        Returns the value of an attribute, checking _managed, _static, and _features.
        For unregistered attributes starting with "has", returns False to support
        feature-flag checks (e.g., data.has_minimap_attributes).
        A Data Key's legacy name reads the key's value.
        """
        owned = self.__dict__.get("_owned")
        if owned is not None and name in owned:
            name = owned[name][0].name
        managed = self.__dict__.get("_managed")
        if managed is not None and name in managed:
            return managed[name].get(self)
        static = self.__dict__.get("_static")
        if static is not None and name in static:
            return static[name]
        features = self.__dict__.get("_features")
        if features is not None and name in features:
            return True
        if name.startswith("has"):
            return False
        raise AttributeError(f"{name} not found in {self}")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Sets the value of a managed or static attribute. For internal attributes
        (ign, _managed, _static, _features, _clock, _owned), falls through to normal
        attribute setting. A Data Key's legacy name sets the key's value.
        """
        if name in self._OWN:
            super().__setattr__(name, value)
            return
        name = self._canonical(name)
        if name in self._managed:
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
        name = self._canonical(name)
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
        name = self._canonical(name)
        if name in self._managed:
            return self._clock() - self._managed[name].metadata.last_valid_update_time
        raise AttributeError(f"{name} not found in {self}")

    def get_time_since_last_value_change(self, name: str) -> float:
        """
        Returns the time since the last value change of an attribute, in seconds:
        infinite when it never changed.
        """
        name = self._canonical(name)
        if name in self._managed:
            return self._clock() - self._managed[name].metadata.last_value_change_time
        raise AttributeError(f"{name} not found in {self}")

    def check_if_values_have_changed(self, name: str) -> bool:
        """
        Checks in the last known value to see if there was any change.
        """
        name = self._canonical(name)
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
        name = self._canonical(name)
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

    def set_feature(self, name: str) -> None:
        """
        Register a feature flag. Accessible as self.name returning True.
        """
        self._features.add(name)

    def remove_feature(self, name: str) -> None:
        """
        Remove a feature flag.
        """
        self._features.discard(name)

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
        in _managed. Use reconfigure_attribute() to modify an existing one, or
        create_or_reconfigure_attribute() for mixin setup methods that may be
        called multiple times.
        :raises OwnedByProvider: a Provider owns `name`.
        """
        self._refuse_owned(name)
        if name in self._managed:
            raise AttributeError(
                f"{name} already exists in {self}. Use reconfigure_attribute()."
            )
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

    def reconfigure_attribute(
        self,
        name: str,
        update_function: Callable[..., Any] | _Unset = _SENTINEL,
        threshold: float | None | _Unset = _SENTINEL,
        error_handler: Callable[..., Any] | None | _Unset = _SENTINEL,
    ) -> None:
        """
        Reconfigure an existing managed attribute. Preserves metadata history.
        Only updates the fields that are explicitly passed. Uses a sentinel
        default so that None can be passed explicitly (e.g., to remove an
        error_handler).
        """
        name = self._canonical(name)
        if name not in self._managed:
            raise AttributeError(f"{name} not found in {self}. Cannot reconfigure.")
        managed = self._managed[name]
        if update_function is not _SENTINEL:
            managed.update_function = update_function
        if threshold is not _SENTINEL:
            managed.threshold = threshold
        if error_handler is not _SENTINEL:
            managed.error_handler = error_handler

    def snapshot_attribute(self, name: str) -> None:
        """
        Records a managed attribute's update configuration so that a temporary
        override (installed with reconfigure_attribute) can later be undone with
        restore_attribute. The first snapshot wins until it is restored.
        """
        name = self._canonical(name)
        if name not in self._managed:
            raise AttributeError(f"{name} not found in {self}. Cannot snapshot.")
        self._managed[name].snapshot_config()

    def restore_attribute(self, name: str) -> None:
        """
        Puts back the update configuration captured by snapshot_attribute(). Does
        nothing when no snapshot is held.
        """
        name = self._canonical(name)
        if name not in self._managed:
            raise AttributeError(f"{name} not found in {self}. Cannot restore.")
        self._managed[name].restore_config()

    def create_or_reconfigure_attribute(
        self,
        name: str,
        update_function: Callable[..., Any],
        threshold: float | None = None,
        initial_value: Any = None,
        error_handler: Callable[..., Any] | None = None,
        max_retries: int = 1,
    ) -> None:
        """
        Creates a new attribute or reconfigures an existing one.
        Used by mixin setup methods that may be called multiple times.
        Preserves metadata on reconfiguration.

        This is a full re-installation of the configuration, so it discards any
        pending snapshot: restore_attribute() must never resurrect an update
        function the owner has since replaced.
        :raises OwnedByProvider: a Provider owns `name`.
        """
        self._refuse_owned(name)
        self._static.pop(name, None)
        if name in self._managed:
            managed = self._managed[name]
            managed._snapshot = None
            managed.update_function = update_function
            managed.threshold = threshold
            managed.error_handler = error_handler
            managed.max_retries = max_retries
        else:
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
        :raises StartupRefused: one of the key's names is already taken by
            another attribute.
        """
        if type(provider) is not key.provider:
            raise ValueError(
                f"{provider} registered {key.name!r}, which "
                f"{key.provider.__name__} provides."
            )
        if self.is_provided(key):
            raise ValueError(f"{provider} registered {key.name!r} twice.")
        for name in key.names():
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
        for name in key.names():
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
        if not self.is_provided(key):
            raise LookupError(
                f"{key!r} has no value in {self}: {key.provider.__name__} was not "
                "built. A key is provided once a DecisionMaker's reads declares it."
            )
        return self._managed[key.name].get(self)

    def peek[T](self, key: Key[T]) -> T | None:
        """
        `key`'s last known value, without refreshing it: the latest one that is
        not empty, or None when there is none, or when `key`'s Provider was not
        built.
        """
        if not self.is_provided(key):
            return None
        return self.get_last_known_value(key.name, update=False)

    def _canonical(self, name: str) -> str:
        """The name a managed attribute is stored under: a key's own for its legacy."""
        owner = self._owned.get(name)
        return owner[0].name if owner is not None else name

    def _refuse_owned(self, name: str) -> None:
        owner = self._owned.get(name)
        if owner is not None:
            key, provider = owner
            raise OwnedByProvider(
                f"{name!r} in {self} is {key!r}, which {provider} provides: read it, "
                "do not create it."
            )
