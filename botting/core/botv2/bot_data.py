from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
import logging

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
    last_update_time: datetime = None  # Timestamp of the last update
    # Last N values of the attribute
    last_values: deque[Any] = field(default_factory=lambda: deque(maxlen=N_RET_VALUES))

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
        "_thresholds"
    }

    def __init__(self, ign: str) -> None:
        self.ign = ign
        self._attributes: dict[str, Any] = {}
        self._metadata: dict[str, AttributeMetadata] = {}
        self._update_functions: dict[str, callable] = {}
        self._thresholds: dict[str, float] = {}

    def __str__(self) -> str:
        return f"BotData({self.ign})"

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
            threshold = self._thresholds[name] or 0.0
            now = datetime.now()
            last_update_time = metadata.last_update_time or datetime.min
            if (now - last_update_time).total_seconds() > threshold:
                logger.log(
                    LOG_LEVEL, f"{self} Updating {name} due to exceeded threshold."
                )
                self.update_attribute(name)
            return self._attributes[name]
        elif name in [*self._authorized_attributes, '_authorized_attributes']:
            return super().__getattribute__(name)
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
            self._metadata[name].last_values.append(value)
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
        metadata = self._metadata[name]
        metadata.update_count += 1
        now = datetime.now()
        metadata.last_update_time = now
        value = self._update_functions[name]()
        self.__setattr__(name, value)
        metadata.total_update_time += (datetime.now() - now).total_seconds()

    def create_attribute(
        self,
        name: str,
        update_function: callable,
        threshold: float = None,
    ) -> None:
        """
        Creates a new attribute or overwrites the specifications of an existing one.
        :param name: Name of the attribute.
        :param update_function: Function to update the attribute.
        :param threshold: Maximum delay after which the attribute is updated.
        :return:
        """
        self._metadata.setdefault(name, AttributeMetadata())
        self._update_functions[name] = update_function
        self._thresholds[name] = threshold
        self._attributes[name] = None
        self.update_attribute(name)
