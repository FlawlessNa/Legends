import asyncio
import logging
import math
import multiprocessing.connection
import multiprocessing.managers

from .mixins import RebuffMixin, NextTargetMixin, MinimapAttributesMixin
from botting import PARENT_LOG
from botting.core import DecisionMaker, BotData
from royals.model.mechanics import RoyalsSkill

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.INFO
from datetime import datetime

_CURRENT_TIME = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class PartyRebuff(MinimapAttributesMixin, NextTargetMixin, RebuffMixin, DecisionMaker):
    _TIME_LIMIT = 120  # An error is triggered after 2 minutes of waiting
    # TODO - Deal with Macros as well.
    # TODO - Could potentially use nested DictProxy or ListProxy within metadata to facilitate synchronization.

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        synchronized_buffs: list[str],
        buff_location: tuple[int, int] = None,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._location = buff_location or self.data.current_minimap.central_node

        # Set the party-buffs specific to the current character
        self._buffs = {
            self.data.character.skills[buff]
            for buff in synchronized_buffs
            if buff in self.data.character.skills
        }
        self._min_duration = min([buff.duration for buff in self._buffs], default=1000)
        self._min_range = min(
            [
                skill.horizontal_minimap_distance
                for skill in self._buffs
                if skill.horizontal_minimap_distance is not None
            ],
            default=5,
        )
        self._all_buffs = synchronized_buffs

        # Set up the synchronization primitives used across bots with this DecisionMaker
        self._condition = self.request_proxy(
            self.metadata, self.__class__.__name__ + "Condition", "Condition", True
        )
        self._event = self.request_proxy(
            self.metadata, self.__class__.__name__ + "Event", "Event", True
        )

        # Unique condition is used by this instance and NOT shared.
        # Used for buff confirmation
        self._unique_condition = self.request_proxy(
            self.metadata, f"{self}", "Condition"
        )

        if not self.data.has_minimap_attributes:
            self._create_minimap_attributes()

        assert self.data.has_minimap_attributes, f"{self} must have minimap attributes"
        location_key = self.__class__.__name__ + "_character_locations"
        rebuff_key = self.__class__.__name__ + "_rebuffed"
        with self._condition:
            if location_key not in self.metadata:
                self.metadata[location_key] = dict()
                self.metadata["ignored_keys"] = self.metadata["ignored_keys"].union(
                    {location_key}
                )
            if rebuff_key not in self.metadata:
                self.metadata[rebuff_key] = dict()
                self.metadata["ignored_keys"] = self.metadata["ignored_keys"].union(
                    {rebuff_key}
                )

        self._set_ready_state()
        self._reset_flag = False

    async def _decide(self, *args, **kwargs) -> None:
        await self._wait_until_ready()
        self._set_fixed_target(self._location)
        try:
            await asyncio.wait_for(
                self._attempt_party_rebuff(), timeout=self._TIME_LIMIT
            )
        except asyncio.TimeoutError as e:
            e.add_note(f"{self} timed out while attempting to party rebuff.")
            raise e

        self._reset_state()

    async def _attempt_party_rebuff(self) -> None:
        """
        Attempt to rebuff the party.
        """
        while True:
            if self._rebuff_status_all_true():
                logger.log(LOG_LEVEL, "All have successfully been rebuffed.")
                with self._condition:
                    self._condition.notify_all()
                break

            self._set_ready_state()
            if self._members_all_in_range():
                logger.log(LOG_LEVEL, f"{self} confirms all members at location.")
                ...  # TODO - Single cast for required members only

            # with self._condition:
            #     print(
            #         f"{_CURRENT_TIME()}: {self} has acquired _condition to update rebuff status and check status"
            #     )
            #     if self._condition.wait_for(self._rebuff_status_all_true, timeout=1):
            #         logger.log(LOG_LEVEL, "All have successfully been rebuffed.")
            #         self._condition.notify_all()
            #         break
            # print(
            #     f"{_CURRENT_TIME()}: {self} has released _condition to update rebuff status and check status"
            # )
            #
            # print(f"{_CURRENT_TIME()}: {self} is setting the event flag")
            # self._set_ready_state()
            # if await asyncio.to_thread(self._wait_for_party_at_location):
            #     logger.log(LOG_LEVEL, f"{self} confirms all members at location.")
            #     # TODO - Change this. If character gets away while attempting to cast, locations are not updated, triggering a timeout.
            #     await self._cast_and_confirm(
            #         list(self._buffs),
            #         self._unique_condition,
            #         predicate=self._own_buff_completed,
            #     )

    def _set_ready_state(self) -> None:
        """
        Set the ready state, shared across all PartyRebuff instances from all processes.
        """
        with self._condition:
            print(
                f"{_CURRENT_TIME()}: {self} has acquired _condition to set the event flag"
            )
            if not self._event.is_set():
                logger.log(LOG_LEVEL, f"{self} signaled its time to rebuff.")
                self._event.set()
                self._reset_shared_location()
                self._reset_rebuff_status()
        print(
            f"{_CURRENT_TIME()}: {self} has released _condition to set the event flag"
        )

    def _reset_state(self) -> None:
        """
        Reset the ready state as well as the rotation mechanism, if necessary.
        """
        with self._condition:
            print(
                f"{_CURRENT_TIME()}: {self} has acquired _condition to reset the event flag"
            )
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

        task_done, _ = await asyncio.wait(
            [self_ready, other_ready], return_when=asyncio.FIRST_COMPLETED
        )

        # If we're done waiting because this member is ready to cast, then set the ready
        # state to notify other members
        if self_ready in task_done:
            print(f"{_CURRENT_TIME()}: {self}: Time to rebuff")
            self._set_ready_state()

    def _wait_for_party_at_location(self) -> bool:
        """
        Wait for the party to be ready to rebuff (e.g. at target location).
        """
        # while True:
        res = False
        with self._condition:
            print(
                f"{_CURRENT_TIME()}: {self} has acquired _condition to update locations and check if all members are in range"
            )
            if self._condition.wait_for(self._members_all_in_range, timeout=1):
                self._condition.notify_all()
                res = True
        print(
            f"{_CURRENT_TIME()}: {self} has released _condition to update locations and check if all members are in range"
        )
        return res

    def _update_shared_location(self) -> None:
        """
        Update the shared location to the current location.
        """
        ident = self.__class__.__name__ + "_character_locations"
        locations = self.metadata[ident]
        locations[f"{self}"] = self.data.current_minimap_position
        print(f"{_CURRENT_TIME()}: {self} updated locations: {locations}")
        self.metadata[ident] = locations

    def _update_rebuff_status(self) -> None:
        """
        Update the rebuffed status for the current member.
        """
        ident = self.__class__.__name__ + "_rebuffed"
        statuses = self.metadata[ident]
        temp = statuses[f"{self}"].copy()
        for buff in temp:
            if self._buff_confirmation(buff):
                statuses[f"{self}"].remove(buff)
        print(f"{_CURRENT_TIME()}: {self} updated status: {statuses}")
        self.metadata[ident] = statuses

    def _reset_shared_location(self) -> None:
        ident = self.__class__.__name__ + "_character_locations"
        locations = self.metadata[ident]
        for key in locations:
            locations[key] = (-100, -100)
        self.metadata[ident] = locations
        print(f"{_CURRENT_TIME()}: {self} reset locations: {locations}")

    def _reset_rebuff_status(self) -> None:
        """
        Reset the rebuffed status for all members.
        """
        ident = self.__class__.__name__ + "_rebuffed"
        statuses = self.metadata[ident]
        for key in statuses:
            statuses[key] = self._all_buffs
        self.metadata[ident] = statuses
        print(f"{_CURRENT_TIME()}: {self} reset rebuff status: {statuses}")

    def _own_buff_completed(self) -> bool:
        """
        Returns False if any other member is still in need of this member's buffs.
        :return:
        """
        ident = self.__class__.__name__ + "_rebuffed"
        buff_names = {buff.name for buff in self._buffs}
        with self._condition:
            self._update_rebuff_status()
            # self._update_shared_location()
            statuses = self.metadata[ident]
        print(f"{_CURRENT_TIME()}: {self} Own Buff Done: {statuses}")
        print(
            f"{_CURRENT_TIME()}: {self} Own Buff Done: {all(not buff_names.intersection(status) for status in statuses.values())}"
        )
        return all(not buff_names.intersection(status) for status in statuses.values())

    def _members_all_in_range(self) -> bool:
        """
        Computes the maximum distance between all shared locations and check if within
        range.
        """
        ident = self.__class__.__name__ + "_character_locations"
        with self._condition:
            # self._update_rebuff_status()
            self._update_shared_location()
            locations = self.metadata[ident].values()
        print(
            f"{_CURRENT_TIME()}: {self} checking members in range: {all(math.dist(location, self._location) <= self._min_range for location in locations) and len(locations) > 1}"
        )
        return (
            all(
                math.dist(location, self._location) <= self._min_range
                for location in locations
            )
            and len(locations) > 1
        )

    def _rebuff_status_all_true(self) -> bool:
        """
        Check if all members have properly been rebuffed.
        :return:
        """
        ident = self.__class__.__name__ + "_rebuffed"
        with self._condition:
            self._update_rebuff_status()
            # self._update_shared_location()
            statuses = self.metadata[ident].values()
        print(f"{_CURRENT_TIME()}: {self} checking rebuff status: {statuses}")
        return all(len(status) == 0 for status in statuses) and len(statuses) > 1


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
        self._decision_task: dict[str, asyncio.Task] = dict()

    async def start(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        """
        Overwrites the DecisionMaker start method such that a new task is created for
        each buff individually.
        :return:
        """
        for buff in self._buffs:
            ident = f"{self} - {buff.name}"
            condition = self.request_proxy(self.metadata, ident, "Condition")
            tg.create_task(
                asyncio.to_thread(self._disabler_task, tg, buff, condition),
                name=f"{ident} - Disabler",
            )
            self._decision_task[ident] = tg.create_task(
                self._task(buff, condition), name=ident
            )

    def _disabler_task(self, tg: asyncio.TaskGroup, *args, **kwargs) -> None:
        """
        Overwrites the DecisionMaker start method such that there is one disabler per
        individual buff.
        :return:
        """
        ident = f"{self} - {args[0].name}"
        while True:
            with self._disabler:
                # When notified, cancel the task
                self._disabler.wait()
                self._decision_task[ident].cancel()

                # Upon next notification, re-enable the task
                self._disabler.wait()
                self._decision_task[ident] = tg.create_task(
                    self._task(*args, **kwargs), name=f"{self}"
                )

    async def _decide(
        self, buff: RoyalsSkill, condition: multiprocessing.managers.ConditionProxy
    ) -> None:
        await self._cast_and_confirm([buff], condition)
        await asyncio.sleep(self._randomized(buff.duration))
