import logging
import numpy as np
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.NOTSET
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
    last_update_time: datetime = datetime.min  # Timestamp of last update
    last_valid_update_time: datetime = datetime.min  # Timestamp of last valid update
    last_value_change_time: datetime = datetime.min  # Timestamp of last value change
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
        update_function: callable,
        threshold: float = None,
        initial_value: Any = None,
        error_handler: callable = None,
        **metadata_kwargs,
    ) -> None:
        self.name = name
        self.value: Any = initial_value
        self.metadata = AttributeMetadata(**metadata_kwargs)
        self.update_function = update_function
        self.threshold = threshold
        self.error_handler = error_handler

    def get(self, owner: "BotData") -> Any:
        """
        Returns the current value, automatically refreshing if the threshold
        has been exceeded since the last update.
        """
        self.metadata.access_count += 1
        threshold = self.threshold or float("inf")
        last_update_time = self.metadata.last_update_time or datetime.min
        if (datetime.now() - last_update_time).total_seconds() > threshold:
            logger.log(
                LOG_LEVEL,
                f"{owner} Updating {self.name} due to exceeded threshold.",
            )
            self.update(owner)
        return self.value

    def set(self, value: Any) -> None:
        """
        Sets the value and appends it to the history of previous values.
        """
        self.value = value
        self.metadata.prev_values.append(value)

    def update(self, owner: "BotData") -> None:
        """
        Refreshes the value by calling the update function. Tracks metadata
        such as update count, timing, validity, and value changes.
        Falls back to the error handler if the update function raises.
        """
        try:
            self._execute_update()
        except Exception as e:
            if self.error_handler is not None:
                self.error_handler()
                logger.info(f"Finished error handling for {self.name}.")
                self.update(owner)
                logger.info(
                    f"Successfully updated {self.name} after error handling."
                )
            else:
                raise e

    def _execute_update(self) -> None:
        """
        Calls the update function, updates metadata, and sets the new value.
        """
        now = datetime.now()
        value = self.update_function()
        self.metadata.update_count += 1
        self.metadata.last_update_time = datetime.now()

        if _update_is_valid(value):
            self.metadata.last_valid_update_time = self.metadata.last_update_time

        if _update_is_change(value, self.value):
            self.metadata.last_value_change_time = self.metadata.last_update_time
        self.set(value)
        self.metadata.total_update_time += (
            datetime.now() - now
        ).total_seconds()


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


class BotData:
    """
    A data container instance used by a Bot instance to enable communication
    between its DecisionMakers. This is achieved by the fact that each DecisionMaker
    assigned to a Bot instance has access to the same BotData instance.

    Attributes are registered via create_attribute() and stored as ManagedAttribute
    instances. Each ManagedAttribute encapsulates the attribute's value, metadata,
    update function, refresh threshold, and optional error handler.

    When a managed attribute is accessed, its threshold is checked and the value is
    automatically refreshed if enough time has passed since the last update.
    """

    def __init__(self, ign: str) -> None:
        self.ign = ign
        self._managed: dict[str, ManagedAttribute] = {}

    def __str__(self) -> str:
        return f"BotData({self.ign})"

    def __getattr__(self, name: str) -> Any:
        """
        Returns the value of a managed attribute, auto-refreshing if needed.
        For unregistered attributes starting with "has", returns False to support
        feature-flag checks (e.g., data.has_minimap_attributes).
        """
        managed = self.__dict__.get("_managed")
        if managed is not None and name in managed:
            return managed[name].get(self)
        if name.startswith("has"):
            return False
        raise AttributeError(f"{name} not found in {self}")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Sets the value of a managed attribute. For non-managed attributes
        (ign, _managed), falls through to normal attribute setting.
        """
        if name in ("ign", "_managed"):
            super().__setattr__(name, value)
        elif name in self._managed:
            self._managed[name].set(value)
        else:
            raise AttributeError(f"{name} created in {self}. Use create_attribute()")

    def get_last_known_value(self, name: str, update: bool = True) -> Any:
        """
        Returns the last known (non-None) value of an attribute, if it exists.
        :param name: Name of the attribute.
        :param update: Whether to enable automatic update.
        :return: Last known value of the attribute.
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
        Returns the time since the last valid update of an attribute.
        :param name: Name of the attribute.
        :return: Time since the last valid update.
        """
        if name in self._managed:
            return (
                datetime.now() - self._managed[name].metadata.last_valid_update_time
            ).total_seconds()
        raise AttributeError(f"{name} not found in {self}")

    def get_time_since_last_value_change(self, name: str) -> float:
        """
        Returns the time since the last value change of an attribute.
        :param name: Name of the attribute.
        :return: Time since the last value change.
        """
        if name in self._managed:
            return (
                datetime.now() - self._managed[name].metadata.last_value_change_time
            ).total_seconds()
        raise AttributeError(f"{name} not found in {self}")

    def check_if_values_have_changed(self, name: str) -> bool:
        """
        Checks in the last known value to see if there was any change.
        """
        if name in self._managed:
            prev_values = self._managed[name].metadata.prev_values
            if all(val == prev_values[-1] or val is None for val in prev_values):
                return False
            else:
                return True

    def update_attributes(self, *names: str) -> None:
        """
        Updates the values of the specified attributes.
        :param names: Name of the attributes.
        :return:
        """
        for name in names:
            self.update_attribute(name)

    def update_attribute(self, name: str) -> None:
        """
        Updates the value of an attribute using the update function mapped to it.
        :param name: Name of the attribute.
        :return:
        """
        if name not in self._managed:
            raise AttributeError(f"{name} not found in {self}")
        self._managed[name].update(self)

    @property
    def _metadata(self) -> dict[str, AttributeMetadata]:
        """Provides access to per-attribute metadata for backward compatibility."""
        return {name: attr.metadata for name, attr in self._managed.items()}

    @property
    def _thresholds(self) -> dict[str, float]:
        """Provides access to per-attribute thresholds for backward compatibility."""
        return {name: attr.threshold for name, attr in self._managed.items()}

    def create_attribute(
        self,
        name: str,
        update_function: callable,
        threshold: float = None,
        initial_value: Any = None,
        error_handler: callable = None,
        **kwargs,
    ) -> None:
        """
        Creates a new attribute or overwrites the specifications of an existing one.
        :param name: Name of the attribute.
        :param update_function: Function to update the attribute.
        :param threshold: Maximum delay after which the attribute is automatically
            refreshed on access.
        :param initial_value: Initial value of the attribute, which bypasses the
            update function if specified.
        :param error_handler: Function to handle errors in the update function.
        :return:
        """
        if name in self._managed:
            managed = self._managed[name]
            managed.update_function = update_function
            managed.threshold = threshold
            managed.error_handler = error_handler
        else:
            self._managed[name] = ManagedAttribute(
                name=name,
                update_function=update_function,
                threshold=threshold,
                initial_value=initial_value,
                error_handler=error_handler,
                **kwargs,
            )
        if initial_value is None:
            self.update_attribute(name)
