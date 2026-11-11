"""
Whether a chat line is meant for the character: it must be answered, the model
judges it, or it is ignored.

- `MUST`: a whisper to us, any party or buddy line (they only reach our party
  and buddies), and a general line whose message names the IGN as a whole word,
  in any case.
- `GM`: a line of kind `gm`, and any later line from a speaker seen as a GM.
  Those speakers are the only state `Addressing` keeps, for the session.
- `JUDGE`: any other general line from someone else. The model decides whether
  it was meant for us, and may stay silent. It passes through `judge_gate`
  first, where how close the speaker is (D9), or how many players are on the
  map, plugs in later.
- `IGNORE`: our own lines, a general line `judge_gate` rejects, and the kinds
  never answered (megaphone, system, `unknown`).
"""

import enum
import re
from collections.abc import Iterable
from dataclasses import dataclass

from maple.screen.chat import ChatKind

from .line import ReadLine, same_name


class Address(enum.Enum):
    GM = "gm"
    MUST = "must"
    JUDGE = "judge"
    IGNORE = "ignore"


STRENGTH: dict[Address, int] = {
    Address.GM: 3,
    Address.MUST: 2,
    Address.JUDGE: 1,
    Address.IGNORE: 0,
}
"""How strongly an address asks for a reply: a burst of lines takes the
strongest of its lines'."""


def strongest(addresses: Iterable[Address]) -> Address:
    """The strongest of `addresses`, by `STRENGTH`."""
    return max(addresses, key=STRENGTH.__getitem__)


_ALWAYS_ANSWERED = frozenset({ChatKind.WHISPER, ChatKind.PARTY, ChatKind.BUDDY})


@dataclass(frozen=True, slots=True)
class Evidence:
    """
    What is known about a general line beyond its text, for `judge_gate`.
    Nothing yet: how close its speaker is (D9) and how many players are on the
    map are added here when they can be read.
    """


NO_EVIDENCE = Evidence()


def judge_gate(line: ReadLine, evidence: Evidence) -> bool:
    """
    Whether a general line not naming us goes to the model to judge. A line it
    rejects is `IGNORE`. Every line passes, for now.
    """
    return True


class Addressing:
    """Classifies the lines of one character's chat. One per bot session."""

    def __init__(self, ign: str) -> None:
        self.ign = ign
        self._named = re.compile(rf"(?<!\w){re.escape(ign)}(?!\w)", re.IGNORECASE)
        self._gms: set[str] = set()

    def classify(self, line: ReadLine, evidence: Evidence = NO_EVIDENCE) -> Address:
        """The line's address. A line of kind `gm` is remembered: its speaker's
        later lines are `GM` too, whatever their kind."""
        if line.outgoing or same_name(line.speaker, self.ign):
            return Address.IGNORE
        if line.kind is ChatKind.GM:
            if line.speaker is not None:
                self._gms.add(line.speaker.casefold())
            return Address.GM
        if line.kind not in _ALWAYS_ANSWERED and line.kind is not ChatKind.GENERAL:
            return Address.IGNORE
        if line.speaker is not None and line.speaker.casefold() in self._gms:
            return Address.GM
        if line.kind in _ALWAYS_ANSWERED:
            return Address.MUST
        if line.message is not None and self._named.search(line.message):
            return Address.MUST
        return Address.JUDGE if judge_gate(line, evidence) else Address.IGNORE
