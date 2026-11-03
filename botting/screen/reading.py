"""The result type every reader returns."""

from __future__ import annotations

import enum
from dataclasses import dataclass


class Status(enum.Enum):
    READ = "read"
    ABSENT = "absent"
    COVERED = "covered"
    UNSURE = "unsure"


@dataclass(frozen=True)
class Reading[T]:
    """What a reader saw. ``value`` is set exactly when ``status`` is ``READ``."""

    value: T | None
    status: Status
    frame_time: float
    detail: str = ""

    def __post_init__(self) -> None:
        if self.status is Status.READ:
            if self.value is None:
                raise ValueError("a READ Reading needs a value")
        elif self.value is not None:
            raise ValueError(f"a {self.status.name} Reading cannot carry a value")

    @classmethod
    def read(cls, value: T, frame_time: float, detail: str = "") -> Reading[T]:
        return cls(value, Status.READ, frame_time, detail)

    @classmethod
    def absent(cls, frame_time: float, detail: str = "") -> Reading[T]:
        return cls(None, Status.ABSENT, frame_time, detail)

    @classmethod
    def covered(cls, frame_time: float, detail: str = "") -> Reading[T]:
        return cls(None, Status.COVERED, frame_time, detail)

    @classmethod
    def unsure(cls, frame_time: float, detail: str = "") -> Reading[T]:
        return cls(None, Status.UNSURE, frame_time, detail)
