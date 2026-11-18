"""
How fast a person types: one delay per character of a message.

A message is typed at one base rate, drawn for that message. Each character's
delay is that rate's interval, jittered, and longer after a space or
punctuation, where a person pauses between words. The pace only spaces the
characters out: what is typed is always the message itself, never a typo.

`controller.write` spends these delays. Nothing here sends input or knows what
is being typed into.
"""

import random
from dataclasses import dataclass, field

SECONDS_PER_MINUTE = 60.0


@dataclass(frozen=True)
class TypingPace:
    """
    A human typing pace. Picklable, so an `ActionRequest` can carry it to Main
    Process.

    :ivar min_cpm: The slowest base rate a message is typed at, in characters per
        minute.
    :ivar max_cpm: The fastest.
    :ivar jitter: How far one character's delay strays from the base interval, as
        a fraction of it either way.
    :ivar min_pause: The least a pause after a space or punctuation multiplies the
        delay by.
    :ivar max_pause: The most it multiplies it by.
    :ivar pause_after: The characters a pause follows.
    :ivar rng: Where every draw comes from. Seed it for a repeatable pace.
    """

    min_cpm: float = 180.0
    max_cpm: float = 260.0
    jitter: float = 0.25
    min_pause: float = 1.5
    max_pause: float = 2.5
    pause_after: frozenset[str] = frozenset(" .,!?;:")
    rng: random.Random = field(default_factory=random.Random, compare=False)

    def __post_init__(self) -> None:
        if not 0 < self.min_cpm <= self.max_cpm:
            raise ValueError(
                f"Rates must satisfy 0 < min_cpm <= max_cpm, got "
                f"{self.min_cpm} and {self.max_cpm}."
            )
        if not 0 <= self.jitter < 1:
            raise ValueError(f"jitter must be in [0, 1), got {self.jitter}.")
        if not 1 <= self.min_pause <= self.max_pause:
            raise ValueError(
                f"Pauses must satisfy 1 <= min_pause <= max_pause, got "
                f"{self.min_pause} and {self.max_pause}."
            )

    def delays(self, message: str) -> list[float]:
        """
        One delay per character of `message`: the time from typing that character
        to typing the next. The base rate is drawn once, for this message.
        :param message: What is about to be typed.
        :return: `len(message)` delays, in seconds, each within `bounds(char)`.
        """
        interval = SECONDS_PER_MINUTE / self.rng.uniform(self.min_cpm, self.max_cpm)
        delays: list[float] = []
        for char in message:
            delay = interval * self.rng.uniform(1 - self.jitter, 1 + self.jitter)
            if char in self.pause_after:
                delay *= self.rng.uniform(self.min_pause, self.max_pause)
            delays.append(delay)
        return delays

    def bounds(self, char: str) -> tuple[float, float]:
        """
        The shortest and longest delay `delays` can give `char`, in seconds.
        :param char: One character.
        :return: `(shortest, longest)`.
        """
        shortest = SECONDS_PER_MINUTE / self.max_cpm * (1 - self.jitter)
        longest = SECONDS_PER_MINUTE / self.min_cpm * (1 + self.jitter)
        if char in self.pause_after:
            return shortest * self.min_pause, longest * self.max_pause
        return shortest, longest
