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
    A data container instance used by BotData to retain the overall frequency of
    updates for each attribute, as well as the average update time and the last
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


class BotData:
    """
    A data container instance used by a Bot instance to enable communication
    between its DecisionMakers. This is achieved by the fact that each DecisionMaker
    assigned to a Bot instance has access to the same BotData instance.

    Whenever an attribute of BotData is created/updated, BotData retains the overall
    frequency of updates for each attribute, as well as the average update time.
    It also retains the last N values of the attribute.
    Lastly, a thresh can be set for each attribute to ensure the attribute is
    automatically updated if the time since the last update is greater than the
    threshold value.
    """

    _authorized_attributes: set[str] = {
        "ign",
        "_attributes",
        "_metadata",
        "_update_functions",
        "_thresholds",
        "_error_handlers",
    }

    def __init__(self, ign: str) -> None:
        self.ign = ign
        self._attributes: dict[str, Any] = {}
        self._metadata: dict[str, AttributeMetadata] = {}
        self._update_functions: dict[str, callable] = {}
        self._thresholds: dict[str, float] = {}
        self._error_handlers: dict[str, callable] = {}

    def __str__(self) -> str:
        return f"BotData({self.ign})"

    def get_last_known_value(self, name: str, update: bool = True) -> Any:
        """
        Returns the last known (non-None) value of an attribute, if it exists.
        :param name: Name of the attribute.
        :param update: Whether to enable automatic update.
        :return: Last known value of the attribute.
        """
        if name in self._metadata:
            last_known_update = next(
                (
                    value
                    for value in reversed(self._metadata[name].prev_values)
                    if value not in [None, "", [], {}]
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
        if name in self._metadata:
            return (
                datetime.now() - self._metadata[name].last_valid_update_time
            ).total_seconds()
        raise AttributeError(f"{name} not found in {self}")

    def get_time_since_last_value_change(self, name: str) -> float:
        """
        Returns the time since the last value change of an attribute.
        :param name: Name of the attribute.
        :return: Time since the last value change.
        """
        if name in self._metadata:
            return (
                datetime.now() - self._metadata[name].last_value_change_time
            ).total_seconds()
        raise AttributeError(f"{name} not found in {self}")

    def __getattr__(self, name: str) -> Any:
        """
        Returns the value of an attribute if it exists, and also updates the metadata
        for that attribute.
        Looks at whether the threshold for updating the attribute has been reached,
        and if so, updates the attribute.
        :param name: Name of the attribute.
        :return:
        """
        if name in self._attributes:
            metadata = self._metadata[name]
            metadata.access_count += 1
            threshold = self._thresholds[name] or float("inf")
            now = datetime.now()
            last_update_time = metadata.last_update_time or datetime.min
            if (now - last_update_time).total_seconds() > threshold:
                logger.log(
                    LOG_LEVEL, f"{self} Updating {name} due to exceeded threshold."
                )
                self.update_attribute(name)
            return self._attributes[name]
        elif name in [*self._authorized_attributes, "_authorized_attributes"]:
            return super().__getattribute__(name)
        elif name.startswith('has'):
            return False
        raise AttributeError(f"{name} not found in {self}")

    def __setattr__(self, name: str, value: Any) -> None:
        """
        Sets the value of an attribute, and also updates the metadata for that attribute
        :param name: Name of the attribute.
        :param value: Value to set.
        :return:
        """
        if name in self._authorized_attributes:
            super().__setattr__(name, value)
        elif name in self._attributes:
            self._attributes[name] = value
            self._metadata[name].prev_values.append(value)
        else:
            raise AttributeError(f"{name} created in {self}. Use create_attribute()")

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
        if name not in self._metadata:
            raise AttributeError(f"{name} not found in {self}")
        try:
            self._update_value(name)
        except Exception as e:
            if name in self._error_handlers:
                self._error_handlers[name]()
                self._update_value(name)
            else:
                raise e

    def _update_value(self, name: str) -> None:
        """
        Updates the value of an attribute.
        :param name: Name of the attribute.
        :return:
        """
        metadata = self._metadata[name]
        now = datetime.now()
        value = self._update_functions[name]()
        metadata.update_count += 1
        metadata.last_update_time = datetime.now()

        if self._update_is_valid(value):
            metadata.last_valid_update_time = metadata.last_update_time

        if self._update_is_change(value, self._attributes[name]):
            metadata.last_value_change_time = metadata.last_update_time
        self.__setattr__(name, value)
        metadata.total_update_time += (datetime.now() - now).total_seconds()

    @staticmethod
    def _update_is_valid(value: Any) -> bool:
        if isinstance(value, np.ndarray):
            return not (np.all(value == 0) or value.size == 0)
        else:
            return value not in [None, "", [], {}, set()]

    @staticmethod
    def _update_is_change(value: Any, prev_value: Any) -> bool:
        if isinstance(value, np.ndarray):
            return not np.all(value == prev_value)
        else:
            return value != prev_value

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
        :param threshold: Maximum delay after which the attribute is updated.
        :param initial_value: Initial value of the attribute, which bypasses the
            update function if specified.
        :param error_handler: Function to handle errors in the update function.
        :return:
        """
        self._metadata.setdefault(name, AttributeMetadata(**kwargs))
        self._update_functions[name] = update_function
        self._thresholds[name] = threshold
        self._attributes.setdefault(name, initial_value)
        if error_handler is not None:
            self._error_handlers[name] = error_handler
        if not initial_value:
            self.update_attribute(name)
