import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import random
import threading
from collections.abc import Iterable, Mapping, Sequence
from functools import partial

from botting import PARENT_LOG
from botting.core import (
    ActionRequest,
    ActionWithValidation,
    BotData,
    DecisionLoop,
    DecisionMaker,
)
from maple.actions import priorities
from maple.actions.skills_related_v2 import cast_skill_single_press
from maple.model.characters import MapleSkill
from maple.screen.buffs import BUFFS

from .buff_confirmation import BuffsReading, CastCheck
from .providers import BUFFS_READING, CHARACTER, FRAME, HANDLE

logger = logging.getLogger(PARENT_LOG + "." + __name__)


def solo_buffs(
    skills: Mapping[str, MapleSkill],
    included_buffs: Iterable[str] | None = None,
    excluded_buffs: Iterable[str] | None = None,
) -> list[MapleSkill]:
    """
    The buffs `SoloRebuff` keeps up: the character's self-buffs used by
    default, plus `included_buffs`, less `excluded_buffs`.
    """
    buffs = [
        skill
        for skill in skills.values()
        if skill.type == "Buff" and skill.use_by_default
    ]
    buffs.extend(skills[buff] for buff in included_buffs or ())
    excluded = set(excluded_buffs or ())
    return [buff for buff in buffs if buff.name not in excluded]


class SoloRebuff(DecisionMaker):
    """
    Keeps the character's buffs up: one loop per buff casts it, confirms the
    cast on the buff's icon (`CastCheck`), then sleeps out 80 to 85 % of its
    duration.
    """

    # TODO - Deal with Macros as well.

    screen_readers = (BUFFS,)
    reads = (HANDLE, CHARACTER, FRAME, BUFFS_READING)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        included_buffs: list[str] | None = None,
        excluded_buffs: list[str] | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._included_buffs = included_buffs
        self._excluded_buffs = excluded_buffs
        #: The buffs it keeps up, from the character's skills. Set by `setup()`.
        self._buffs: list[MapleSkill] = []
        #: One per buff, made once: a restart after a Pause reuses it.
        self._conditions: dict[str, threading.Condition] = {}

    def setup(self) -> None:
        self._buffs = solo_buffs(
            self.read(CHARACTER).skills, self._included_buffs, self._excluded_buffs
        )
        self._conditions = {
            buff.name: self._proxies.instance(f"{self} - {buff.name}", "Condition")
            for buff in self._buffs
        }

    def loops(self) -> Sequence[DecisionLoop]:
        """
        One decision loop per buff, instead of the base class's single one.

        Each buff has its own duration, so each needs its own clock. The
        Supervisor runs them on the base class's machinery: the loops mint their
        own Correlation IDs and log under their own names, and a Pause on
        `SoloRebuff` stops and restarts them all.
        """
        return [
            DecisionLoop(
                f"{self} - {buff.name}",
                partial(self._recast, buff, self._conditions[buff.name]),
            )
            for buff in self._buffs
        ]

    async def _recast(self, buff: MapleSkill, condition: threading.Condition) -> None:
        """One buff's decision: cast it, then sleep out its duration."""
        await self._cast_and_confirm([buff], condition)
        await asyncio.sleep(self._randomized(buff.duration))

    async def _decide(self) -> None:
        """
        Never called: this DecisionMaker's loops are per-buff and run `_recast`.
        The base class still requires the method.
        """

    def _read_buffs(self) -> BuffsReading:
        """The profile's buffs in a frame captured now."""
        self.refresh(FRAME)
        return self.refresh(BUFFS_READING)

    async def _cast_and_confirm(
        self, buffs: list[MapleSkill], condition: threading.Condition
    ) -> None:
        """
        Cast the buffs, and cast again while one is `NOT_CONFIRMED`.

        The buffs are read from a frame captured before the cast is sent, and
        from one captured after it (`CastCheck`).
        """
        names = [buff.name for buff in buffs]
        predicate = CastCheck(self._read_buffs, names, owner=self)
        request = ActionRequest(
            f"{self} - {names}",
            self._cast_skills_single_press,
            self.data.ign,
            priority=priorities.BUFFS,
            block_lower_priority=True,
            args=(self.read(HANDLE), self.data.ign, buffs),
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
        """
        return duration * (0.8 + 0.05 * random.random())

    @staticmethod
    async def _cast_skills_single_press(
        handle: int, ign: str, skills: list[MapleSkill]
    ) -> None:
        for skill in skills:
            await cast_skill_single_press(handle, ign, skill)
