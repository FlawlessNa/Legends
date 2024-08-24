import asyncio
import logging
import math
import multiprocessing.connection
import multiprocessing.managers

from .mixins import RebuffMixin, NextTargetMixin
from botting import PARENT_LOG
from botting.core import ActionRequest, ActionWithValidation, DecisionMaker, BotData
from royals.model.mechanics import RoyalsSkill
from royals.actions.skills_related_v2 import cast_skill_single_press
from royals.actions import priorities

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.INFO


class PartyRebuff(NextTargetMixin, RebuffMixin, DecisionMaker):
    _TIME_LIMIT = 120  # An error is triggered after 2 minutes of waiting
    # TODO - Deal with Macros as well.

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        synchronized_buffs: list[str] = None,
        buff_location: tuple[int, int] = None,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)

        self._location = buff_location or self.data.current_minimap.central_node

        # Set the party-buffs specific to the current character
        buffs = set()
        for buff in synchronized_buffs or []:
            if buff in self.data.character.skills:
                buffs.add(self.data.character.skills[buff])
        self._buffs = buffs
        self._min_duration = min([buff.duration for buff in self._buffs], default=1000)
        self._min_range = min(
            [
                skill.horizontal_minimap_distance
                for skill in self._buffs
                if skill.horizontal_minimap_distance is not None
            ],
            default=5,
        )
        self._all_buff_icons = [
            self._get_buff_icon(buff) for buff in synchronized_buffs
        ]

        # Set up the synchronization primitives used across bots with this DecisionMaker
        self._condition = self.request_proxy(
            self.metadata, self.__class__.__name__ + 'Condition', "Condition", True
        )
        self._event = self.request_proxy(
            self.metadata, self.__class__.__name__ + 'Event', "Event", True
        )
        self._set_ready_state()
        with self._condition:
            self._update_shared_location()

        self._reset_flag = False

    async def _decide(self, *args, **kwargs) -> None:
        await self._wait_until_ready()
        self._set_target_to_buff_location()
        try:
            await asyncio.wait_for(
                asyncio.to_thread(self._wait_for_party_at_location),
                timeout=self._TIME_LIMIT
            )
        except asyncio.TimeoutError:
            logger.error(f"{self} - Timeout reached while waiting for party.")
            raise asyncio.TimeoutError(
                f"{self} - Timeout reached while waiting for party."
            )
        breakpoint()
        # await self._cast_and_confirm()
        self._reset_state()

    def _set_ready_state(self) -> None:
        """
        Set the ready state, shared across all PartyRebuff instances from all processes.
        """
        with self._condition:
            if not self._event.is_set():
                logger.log(LOG_LEVEL, f"{self} signaled its time to rebuff.")
                self._event.set()

    def _reset_state(self) -> None:
        """
        Reset the ready state as well as the rotation mechanism, if necessary.
        """
        with self._condition:
            if self._event.is_set():
                logger.log(LOG_LEVEL, f"{self} resets the ready state.")
                self._event.clear()
        if self._reset_flag:
            self._create_rotation_attributes()  # Resets the rotation mechanism
            self._reset_flag = False

    async def _wait_until_ready(self) -> None:
        """
        Wait until the party is ready to rebuff.
        This occurs when one member sets the event OR when this member is ready.
        """
        self_ready = asyncio.create_task(
            asyncio.sleep(self._randomized(self._min_duration))
        )
        other_ready = asyncio.create_task(asyncio.to_thread(self._event.wait))

        task_done, task_pending = await asyncio.wait(
            [self_ready, other_ready], return_when=asyncio.FIRST_COMPLETED
        )

        # If we're done waiting because this member is ready to cast, then set the ready
        # state to notify other members
        task_done = task_done.pop()
        if task_done is self_ready:
            self._set_ready_state()

    def _set_target_to_buff_location(self) -> None:
        """
        Move to the location where the buffs are cast.
        """
        if math.dist(
            self.data.current_minimap_position, self._location
        ) > self._min_range:
            assert self.data.has_rotation_attributes, (
                "Character must have rotation attributes. This is usually set with a "
                "Rotation DecisionMaker"
            )
            # Overwrite how the next_target attribute is set until the rebuff is done
            self.data.create_attribute(
                'next_target',
                lambda: self._location,
            )
            self._reset_flag = True

    def _wait_for_party_at_location(self) -> None:
        """
        Wait for the party to be ready to rebuff (e.g. at target location).
        """
        while True:
            with self._condition:
                self._update_shared_location()
                success = self._condition.wait_for(
                    self._members_all_in_range, timeout=1
                )
                if success:
                    break

    def _update_shared_location(self) -> None:
        """
        Update the shared location to the current location.
        """
        assert self.data.has_minimap_attributes, f"{self} must have minimap attributes"
        ident = self.__class__.__name__ + '_character_locations'
        if ident not in self.metadata:
            self.metadata[ident] = dict()
            self.metadata["ignored_keys"] = self.metadata["ignored_keys"].union({ident})

        locations = self.metadata[ident]
        locations[f"{self}"] = self.data.current_minimap_position
        self.metadata[ident] = locations

    def _members_all_in_range(self) -> bool:
        """
        Computes the maximum distance between all shared locations and check if within
        range.
        """
        ident = self.__class__.__name__ + '_character_locations'
        locations = self.metadata[ident].values()
        return all(
            math.dist(location, self._location) <= self._min_range
            for location in locations
        )


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
