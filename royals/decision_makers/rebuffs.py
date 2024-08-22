import asyncio
import random
import multiprocessing.connection
import multiprocessing.managers
from .mixins import RebuffMixin, SharedProxyMixin
from botting.core import ActionRequest, ActionWithValidation, DecisionMaker, BotData
from royals.model.mechanics import RoyalsSkill
from royals.actions.skills_related_v2 import cast_skill_single_press
from royals.actions import priorities


class PartyRebuff(SharedProxyMixin, RebuffMixin, DecisionMaker):
    pass

    async def _decide(self, *args, **kwargs) -> None:
        pass


class SoloRebuff(RebuffMixin, DecisionMaker):
    # TODO - Deal with Macros as well.

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        included_buffs: list[str] = None,
        excluded_buffs: list[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)

        # Set up the buffs to be used
        buffs = self._get_character_default_buffs("Buff")
        if included_buffs:
            buffs.extend([self.data.character.skills[buff] for buff in included_buffs])
        if excluded_buffs:
            buffs = list(filter(lambda buff: buff.name not in excluded_buffs, buffs))
        self._buffs = buffs

    async def start(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        """
        Overwrites the DecisionMaker start method such that a new task is created for
        each buff individually.
        :return:
        """
        for buff in self._buffs:
            ident = f"{self} - {buff.name}"
            condition = self.request_proxy(self.metadata, ident, "Condition")
            tg.create_task(super().start(tg, buff, condition), name=ident)

    async def _decide(
        self, buff: RoyalsSkill, condition: multiprocessing.managers.ConditionProxy
    ) -> None:
        await self._cast_and_confirm(buff, condition)
        await asyncio.sleep(self._randomized(buff.duration))

    async def _cast_and_confirm(
        self,
        buff: RoyalsSkill,
        condition: multiprocessing.managers.ConditionProxy,  # noqa
    ) -> None:
        """
        Cast the buff and confirm that it was successful.
        :param buff: The buff to cast.
        :return:
        """
        request = ActionRequest(
            f"{self} - {buff.name}",
            cast_skill_single_press,
            self.data.ign,
            priority=priorities.BUFFS,
            block_lower_priority=True,
            args=(self.data.handle, self.data.ign, buff),
        )
        validator = ActionWithValidation(
            self.pipe,
            lambda: self._buff_confirmation(buff),
            condition,
            timeout=10.0,
            max_trials=10,
        )
        await validator.execute_async(request)
        # validator.execute_blocking(request)

    @staticmethod
    def _randomized(duration: float) -> float:
        """
        Pick a random point within 90% and 95% of the buff's duration.
        :param duration: The duration of the buff.
        :return:
        """
        return duration * (0.9 + 0.05 * random.random())
