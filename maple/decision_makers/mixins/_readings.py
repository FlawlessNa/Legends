"""
What a consumer with no policy for a misread does with a `Reading` (#302,
"Wiring into the training bot"): it reads `.status` before `.value`, keeps the
value it had when the status isn't `READ`, and logs the status at debug level,
once per change. That was the old readers' behaviour, silently; it is now
visible.
"""

import logging
from collections.abc import Callable

from botting import PARENT_LOG
from botting.screen import Reading, Status

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class HeldReading[T, V]:
    """
    A value taken from successive `Reading`s.

    :param owner: Who reads, in the log line.
    :param name: What is read, in the log line.
    :param value_of: The value kept, from a `READ` reading's value.
    :param initial: The value until the first `READ`.
    :param absent: When given, the value an `ABSENT` reading sets, for a
        consumer asking whether its element is shown: not being on screen is an
        answer, not a misread.
    """

    def __init__(
        self,
        owner: object,
        name: str,
        value_of: Callable[[T], V],
        initial: V,
        absent: Callable[[], V] | None = None,
    ) -> None:
        self._owner = owner
        self._name = name
        self._value_of = value_of
        self._absent = absent
        self.value = initial
        self._status: Status | None = None

    def __call__(self, reading: Reading[T]) -> V:
        """The value after `reading`: its own when `READ`, else the one kept."""
        if reading.status is not self._status:
            self._status = reading.status
            logger.debug(
                "%s: %s %s (%s)",
                self._owner,
                self._name,
                reading.status.value,
                reading.detail or "no detail",
            )
        if reading.status is Status.READ and reading.value is not None:
            self.value = self._value_of(reading.value)
        elif reading.status is Status.ABSENT and self._absent is not None:
            self.value = self._absent()
        return self.value
