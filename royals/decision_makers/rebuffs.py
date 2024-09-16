import asyncio
import logging
import math
import multiprocessing.connection
import multiprocessing.managers

from .mixins import RebuffMixin, NextTargetMixin, MinimapAttributesMixin
from botting import PARENT_LOG
from botting.core import ActionRequest, DecisionMaker, BotData
from botting.utilities import cooldown
from royals.actions import priorities
from royals.model.mechanics import RoyalsSkill

logger = logging.getLogger(PARENT_LOG + "." + __name__)
LOG_LEVEL = logging.INFO


class PartyRebuff(MinimapAttributesMixin, NextTargetMixin, RebuffMixin, DecisionMaker):
    _TIME_LIMIT = 120  # An error is triggered after 2 minutes of waiting
    # TODO - Deal with Macros as well.

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
        self._shared_lock = self.request_proxy(
            self.metadata, self.__class__.__name__ + "Lock", "Lock", True
        )
        self._event = self.request_proxy(
            self.metadata, self.__class__.__name__ + "Event", "Event", True
        )

        # Unique Lock is used by this instance and NOT shared.
        # Used for buff confirmation
        self._unique_lock = self.request_proxy(self.metadata, f"{self}", "Lock")

        if not self.data.has_minimap_attributes:
            self._create_minimap_attributes()

        assert self.data.has_minimap_attributes, f"{self} must have minimap attributes"
        location_key = self.__class__.__name__ + "_character_locations"
        rebuff_key = self.__class__.__name__ + "_rebuffed"
        with self._shared_lock:
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

    @cooldown(3.0)
    def cast_buffs(self, remaining_buffs: list) -> None:
        """
        Sends the request but only if the cooldown has passed.
        :param remaining_buffs:
        :return:
        """
        to_cast = [self.data.character.skills[buff] for buff in remaining_buffs]
        self.pipe.send(
            ActionRequest(
                f"{self} - {remaining_buffs}",
                self._cast_skills_single_press,
                self.data.ign,
                priority=priorities.BUFFS,
                block_lower_priority=True,
                args=(self.data.handle, self.data.ign, to_cast),
                callbacks=[self._unique_lock.release],
            )
        )

    async def _attempt_party_rebuff(self) -> None:
        """
        Attempt to rebuff the party.
        """
        while True:
            if self._rebuff_status_all_true():
                logger.log(LOG_LEVEL, "All have successfully been rebuffed.")
                break

            self._event.set()
            if self._members_all_in_range():
                logger.log(LOG_LEVEL, f"{self} confirms all members at location.")
                while not self._unique_lock.acquire(blocking=False):
                    self._update_rebuff_status()
                    await asyncio.sleep(0.1)
                remaining_buffs = self._get_own_buff_remaining()
                if remaining_buffs:
                    if self.cast_buffs(remaining_buffs) is False:
                        # Means the cooldown has not passed, so manually release
                        self._unique_lock.release()
                else:
                    self._unique_lock.release()

            await asyncio.sleep(0.5)

    def _set_ready_state(self) -> None:
        """
        Set the ready state, shared across all PartyRebuff instances from all processes.
        """
        with self._shared_lock:
            if not self._event.is_set():
                logger.log(LOG_LEVEL, f"{self} signaled its time to rebuff.")
                self._event.set()
                self._reset_shared_location()
                self._reset_rebuff_status()

    def _reset_state(self) -> None:
        """
        Reset the ready state as well as the rotation mechanism, if necessary.
        """
        with self._shared_lock:
            if self._event.is_set():
                logger.log(LOG_LEVEL, f"{self} resets the ready state.")
                self._event.clear()
        if self._reset_flag:
            # Resets the rotation mechanism
            self._create_rotation_attributes(self.data.feature_cycle)
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
            self._set_ready_state()

    def _update_shared_location(self) -> None:
        """
        Update the shared location to the current location.
        """
        ident = self.__class__.__name__ + "_character_locations"
        locations = self.metadata[ident]
        locations[f"{self}"] = self.data.current_minimap_position
        self.metadata[ident] = locations

    def _update_rebuff_status(self) -> None:
        """
        Update the rebuffed status for the current member.
        """
        ident = self.__class__.__name__ + "_rebuffed"
        statuses = self.metadata[ident]
        temp = statuses.setdefault(f"{self}", self._all_buffs.copy()).copy()
        for buff in self._all_buffs.copy():
            if self._buff_confirmation(buff) and buff in temp:
                temp.remove(buff)
        statuses[f"{self}"] = temp
        self.metadata[ident] = statuses

    def _reset_shared_location(self) -> None:
        ident = self.__class__.__name__ + "_character_locations"
        locations = self.metadata[ident]
        for key in locations:
            locations[key] = (-100, -100)
        self.metadata[ident] = locations

    def _reset_rebuff_status(self) -> None:
        """
        Reset the rebuffed status for all members.
        """
        ident = self.__class__.__name__ + "_rebuffed"
        statuses = self.metadata[ident]
        for key in statuses:
            statuses[key] = self._all_buffs
        self.metadata[ident] = statuses

    def _get_own_buff_remaining(self) -> list[str]:
        """
        Get the list of buffs that still need to be cast, which is the intersection
        with this member's own buffs and all the other member's remaining buffs.
        :return:
        """

        ident = self.__class__.__name__ + "_rebuffed"
        buff_names = {buff.name for buff in self._buffs}
        statuses = self.metadata[ident]
        remaining = set([item for sublist in statuses.values() for item in sublist])
        return list(buff_names.intersection(remaining))

    def _members_all_in_range(self) -> bool:
        """
        Computes the maximum distance between all shared locations and check if within
        range.
        """
        ident = self.__class__.__name__ + "_character_locations"
        with self._shared_lock:
            self._update_shared_location()
            locations = self.metadata[ident].values()
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
        with self._shared_lock:
            self._update_rebuff_status()
            statuses = self.metadata[ident].values()
            logger.log(LOG_LEVEL, f"Rebuff statuses: {statuses}")
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
