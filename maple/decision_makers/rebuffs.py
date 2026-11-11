import asyncio
import logging
import multiprocessing.connection
import multiprocessing.managers
import threading
from collections.abc import Iterable, Mapping, Sequence
from functools import partial

from botting import PARENT_LOG
from botting.core import BotData, DecisionLoop, DecisionMaker
from maple.model.characters import MapleSkill
from maple.screen.buffs import BUFFS

from .mixins import RebuffMixin

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


class SoloRebuff(RebuffMixin, DecisionMaker):
    # TODO - Deal with Macros as well.

    screen_readers = (BUFFS,)

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

        self._buffs = solo_buffs(
            self.data.character.skills, included_buffs, excluded_buffs
        )
        # One per buff, made once: a restart after a Pause reuses it.
        self._conditions: dict[str, threading.Condition] = {
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
