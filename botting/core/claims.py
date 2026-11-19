"""
Claims: scoped, exclusive rights to steer a steerable Data Key.

A Data Key declared `steerable` is served by its Provider, or, while a
DecisionMaker holds a **Claim** on it, by the value source that DecisionMaker
claimed it with::

    async with self.claim(DESTINATION, fixed(spot), reason="rebuff spot"):
        ...

What is claimed is a value source, not a value, so the key keeps refreshing on
its own threshold while it is claimed. When the Claim is released, by any route,
the key serves its Provider's own value again: the one it served when the Claim
was taken, refreshed on its threshold from its Provider's own update.

The value lives where every key's does, in `BotData` (`BotData.claim`,
`BotData.release`); `DecisionMaker.claim` is the scoped way to hold one.

ADR 0004 records the decisions this module implements.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from botting.telemetry_events import ClaimPayload

if TYPE_CHECKING:
    from .data_keys import Key, Provider

#: Where a claimed key's values come from: called with the key's Provider at
#: every refresh while the Claim is held, it returns the key's value. A source
#: that needs no Provider ignores it (`fixed`, `following`); one that steers the
#: Provider into another of its modes calls it (`DESTINATION`'s `wander`).
type Source[T] = Callable[[Provider], T]


def fixed[T](value: T) -> Source[T]:
    """A source that serves `value`, at every refresh."""
    return lambda _provider: value


def following[T](read: Callable[[], T]) -> Source[T]:
    """A source that serves whatever `read` returns, called at every refresh."""
    return lambda _provider: read()


class ClaimHeld(Exception):
    """
    A Claim was asked for on a key another holder already claims. Claims are
    exclusive and refuse at once: a DecisionMaker that wants to wait does so
    explicitly.
    """


class ClaimNotDeclared(Exception):
    """A DecisionMaker claimed a key its `steers` declaration does not name."""


@dataclass(eq=False)
class Claim:
    """
    One hold on one steerable key. Compared by identity.

    Made by `BotData.claim`, which keeps what to put back when it is released.
    """

    key: Key[Any]
    #: `repr` of the holding DecisionMaker.
    holder: str
    reason: str

    def __str__(self) -> str:
        return f"{self.key.name!r} claimed by {self.holder} ({self.reason})"

    def payload(self) -> ClaimPayload:
        """The `data.claimed` / `data.released` payload for this Claim."""
        return {"key": self.key.name, "holder": self.holder, "reason": self.reason}
