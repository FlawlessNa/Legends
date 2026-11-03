"""
Casting buffs, and confirming the cast took effect by the buff's icon (D9, R1).

A cast is judged by comparing the buffs read from a frame captured before it
was sent with those read after:

- `CONFIRMED`: the buff went from not shown to shown; or it was shown, and came
  back fresh, its `elapsed` dropping by more than `FreshnessMargins.drop`.
- `NOT_CONFIRMED`: it is still not shown, or still shown with no such drop.
- `UNSURE`: freshness can't be judged. A frame before or after wasn't read, a
  buff shown in both has no `elapsed`, or it was recast while nearly fresh, so
  no drop could show.

Only `NOT_CONFIRMED` is retried. `UNSURE` is logged and kept. MP isn't used: MP
regeneration, potions and Magic Guard all move it.
"""

import enum
import logging
import multiprocessing.connection
import random
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from botting import PARENT_LOG
from botting.core import ActionRequest, ActionWithValidation, BotData
from botting.screen import Reading, Status
from maple.actions import priorities
from maple.actions.skills_related_v2 import cast_skill_single_press
from maple.model.characters import MapleBuff, MaplePartyBuff, MapleSkill
from maple.screen.buffs import BuffState

logger = logging.getLogger(PARENT_LOG + "." + __name__)

type BuffsReading = Reading[dict[str, BuffState]]


class Confirmation(enum.Enum):
    CONFIRMED = "confirmed"
    NOT_CONFIRMED = "not_confirmed"
    UNSURE = "unsure"


@dataclass(frozen=True, slots=True)
class FreshnessMargins:
    """
    :ivar drop: A recast is confirmed when `elapsed` drops by more than this.
    :ivar nearly_fresh: A buff whose `elapsed` was below this before the cast
        was recast nearly fresh: no drop could show, so it is `UNSURE`.
    """

    drop: float
    nearly_fresh: float


FRESHNESS_MARGINS: FreshnessMargins | None = None
"""Not chosen yet: they are to be chosen on frames of each buff fresh, mid-way
and nearly expired, which don't exist yet (#312). Until then, and while
`elapsed` is `None`, a buff shown before and after its cast is `UNSURE`."""


def buff_confirmation(
    before: BuffsReading,
    after: BuffsReading,
    buff: str,
    margins: FreshnessMargins | None = FRESHNESS_MARGINS,
) -> Confirmation:
    """Whether the cast of `buff` between `before` and `after` took effect."""
    if (
        before.status is not Status.READ
        or after.status is not Status.READ
        or before.value is None
        or after.value is None
        or buff not in before.value
        or buff not in after.value
    ):
        return Confirmation.UNSURE
    was, now = before.value[buff], after.value[buff]
    if not now.shown:
        return Confirmation.NOT_CONFIRMED
    if not was.shown:
        return Confirmation.CONFIRMED
    if margins is None or was.elapsed is None or now.elapsed is None:
        return Confirmation.UNSURE
    if was.elapsed < margins.nearly_fresh:
        return Confirmation.UNSURE
    if was.elapsed - now.elapsed > margins.drop:
        return Confirmation.CONFIRMED
    return Confirmation.NOT_CONFIRMED


class CastCheck:
    """
    The predicate `ActionWithValidation` calls before each cast and after it.

    `ActionWithValidation` calls it first, before sending anything: that call
    keeps the reading as the "before" frame and asks for the cast. Each later
    call judges the cast just sent against the reading before it, and keeps its
    own reading as the "before" of the next attempt. It asks for another cast
    only when a buff is `NOT_CONFIRMED`.
    """

    def __init__(
        self,
        read: Callable[[], BuffsReading],
        buffs: Sequence[str],
        confirm: Callable[[BuffsReading, BuffsReading, str], Confirmation] = (
            buff_confirmation
        ),
        owner: object = None,
    ) -> None:
        self._read = read
        self._buffs = tuple(buffs)
        self._confirm = confirm
        self._owner = owner
        self._before: BuffsReading | None = None
        self.last: dict[str, Confirmation] = {}

    def __call__(self) -> bool:
        reading = self._read()
        before, self._before = self._before, reading
        if before is None:
            return False
        self.last = {buff: self._confirm(before, reading, buff) for buff in self._buffs}
        if Confirmation.NOT_CONFIRMED in self.last.values():
            return False
        for buff, result in self.last.items():
            if result is Confirmation.UNSURE:
                logger.info(
                    "%s: %s cast but unconfirmed (before: %s %s, after: %s %s); "
                    "not retried",
                    self._owner,
                    buff,
                    before.status.name,
                    before.detail,
                    reading.status.name,
                    reading.detail,
                )
        return True


class RebuffMixin:
    data: BotData
    pipe: multiprocessing.connection.Connection
    correlation_id: str | None

    def _get_character_default_buffs(
        self, buff_type: str
    ) -> list[MapleBuff | MaplePartyBuff]:
        return [
            skill
            for skill in self.data.character.skills.values()
            if skill.type == buff_type and skill.use_by_default
        ]

    def _read_buffs(self, buffs: Sequence[str]) -> BuffsReading:
        """The buffs in a frame captured now. The DecisionMaker must name
        `BUFFS` in its `screen_readers`, so the reader exists."""
        self.data.update_attribute("current_frame")
        return self.data.buffs_reader.read(self.data.current_frame, buffs)

    def _buff_confirmation(
        self, before: BuffsReading, after: BuffsReading, buff: str
    ) -> Confirmation:
        return buff_confirmation(before, after, buff)

    async def _cast_and_confirm(
        self,
        buffs: list[MapleSkill],
        condition: threading.Condition,
        predicate: Callable[[], bool] | None = None,
    ) -> None:
        """
        Cast the buffs, and cast again while one is `NOT_CONFIRMED`.

        The buffs are read from a frame captured before the cast is sent, and
        from one captured after it (`CastCheck`).
        """
        names = [buff.name for buff in buffs]
        if predicate is None:
            predicate = CastCheck(
                lambda: self._read_buffs(names),
                names,
                self._buff_confirmation,
                owner=self,
            )
        request = ActionRequest(
            f"{self} - {names}",
            self._cast_skills_single_press,
            self.data.ign,
            priority=priorities.BUFFS,
            block_lower_priority=True,
            args=(self.data.handle, self.data.ign, buffs),
        )
        validator = ActionWithValidation(
            self.pipe,
            predicate,
            condition,
            timeout=15.0,
            max_trials=20,
            correlation_id=self.correlation_id,
        )
        await validator.execute_async(request)

    @staticmethod
    def _randomized(duration: float) -> float:
        """
        Pick a random point within 80% and 85% of the buff's duration.
        :param duration: The duration of the buff.
        :return:
        """
        return duration * (0.8 + 0.05 * random.random())

    @staticmethod
    async def _cast_skills_single_press(
        handle: int, ign: str, skills: list[MapleSkill]
    ) -> None:
        for skill in skills:
            await cast_skill_single_press(handle, ign, skill)
