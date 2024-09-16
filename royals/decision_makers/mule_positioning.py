import asyncio
import logging
import math
import random
import multiprocessing.connection
import multiprocessing.managers

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from botting.utilities import cooldown
from royals.actions.movements_v2 import random_jump
from royals.actions import priorities
from .mixins import MinimapAttributesMixin, MovementsMixin, RebuffMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO


class EnsureSafeSpot(MinimapAttributesMixin, DecisionMaker):
    """
    Basic DecisionMaker that ensures character has not moved.
    Useful for leeching mules in case they get hit.
    It triggers a discord notification whenever the character has moved.
    """

    _throttle = 2.0

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)

        # Minimap attributes
        self._create_minimap_attributes()
        self._prev_minimap_position = self.data.current_minimap_position

    async def _decide(self) -> None:
        self.data.update_attribute("current_minimap_position")

        if self.data.current_minimap_position != self._prev_minimap_position:
            self._send_alert()

        self._prev_minimap_position = self.data.current_minimap_position

    @cooldown(60)
    def _send_alert(self):
        logger.log(LOG_LEVEL, f"{self.data.ign} has been moved!")
        self.pipe.send(self._discord_alert())

    def _discord_alert(self) -> ActionRequest:
        """
        :return:
        """
        alert = DiscordRequest(
            f"{self.data.ign} has been moved!", self.data.current_client_img
        )

        return ActionRequest(
            f"{self} - Failsafe",
            asyncio.sleep,
            ign=self.data.ign,
            priority=10,
            discord_request=alert,
            args=(0,),
        )


class ResetIdleSafeguard(
    MinimapAttributesMixin, MovementsMixin, RebuffMixin, DecisionMaker
):
    """
    DecisionMaker that moves character at every interval.
    Used to ensure actions such as rebuffing still go through after some time.
    """

    _TIME_LIMIT = 240.0
    DISTANCE_THRESHOLD = 2

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        skills_to_reset: list[str] = None,
        movements_duration: float = 1.0,
        **kwargs,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self.lock = self.request_proxy(self.metadata, f"{self}", "Lock")
        self._teleport_skill = self.data.character.skills.get("Teleport")

        # Minimap attributes
        self._create_minimap_attributes()

        # Rotation attributes
        self._target_position = self.data.current_minimap_position
        self.data.create_attribute(
            "next_target",
            lambda: self._target_position,
            initial_value=self._target_position,
        )
        self._create_pathing_attributes(movements_duration)
        self.data.create_attribute("action", self._always_release_keys_on_actions)

        self._feature = self.data.current_minimap.get_feature_containing(
            self._target_position
        )
        if skills_to_reset:
            self._skills = [
                self.data.character.skills[skill] for skill in skills_to_reset
            ]
        else:
            self._skills = [
                random.choice(
                    [
                        skill
                        for skill in self.data.character.skills.values()
                        if skill.type in ["Buff"]
                    ]
                )
            ]

    async def _decide(self) -> None:
        try:
            await asyncio.wait_for(
                self._ensure_safe_spot(),
                timeout=random.uniform(0.9, 1.1) * self._TIME_LIMIT,
            )
            logger.log(LOG_LEVEL, f"{self} is not at safe spot. Resetting")
        except asyncio.TimeoutError:
            logger.log(LOG_LEVEL, f"{self} is idle. Engaging reset.")

        await self._jump_out_of_safe_spot()
        await self._cast_skills_to_reset()
        self._disable_decision_makers("Rotation")
        await self._return_to_safe_spot()
        self._enable_decision_makers("Rotation")

    async def _ensure_safe_spot(self) -> None:
        while True:
            if not self._is_at_safe_spot():
                break
            await asyncio.sleep(5)

    async def _jump_out_of_safe_spot(self) -> None:
        num_jumps = random.randint(2, 4)
        for _ in range(num_jumps):
            await asyncio.to_thread(self.lock.acquire)
            self.pipe.send(
                ActionRequest(
                    f"{self} - Jumping Out of Rope",
                    random_jump(
                        self.data.handle, controller.key_binds(self.data.ign)["jump"]
                    ).send,
                    ign=self.data.ign,
                    callbacks=[self.lock.release],
                    priority=priorities.MULE_POSITIONING,
                    block_lower_priority=True,
                    log=True,
                )
            )
            await asyncio.sleep(1.0)

    async def _cast_skills_to_reset(self) -> None:
        """Required to remove the game safeguard"""
        await asyncio.to_thread(self.lock.acquire)
        self.pipe.send(
            ActionRequest(
                f"{self} - Casting Random Buff",
                self._cast_skills_single_press,
                ign=self.data.ign,
                callbacks=[self.lock.release],
                priority=priorities.MULE_POSITIONING,
                block_lower_priority=True,
                args=(self.data.handle, self.data.ign, self._skills),
                log=True,
            )
        )

    def _is_at_safe_spot(self) -> bool:
        print(self.data.current_minimap_position, self._target_position)
        return (
            math.dist(self.data.current_minimap_position, self._target_position)
            < self.DISTANCE_THRESHOLD
            and self.data.current_minimap.get_feature_containing(
                self.data.current_minimap_position
            )
            == self._feature
        )

    async def _return_to_safe_spot(self) -> None:
        while not self._is_at_safe_spot():
            await asyncio.to_thread(self.lock.acquire)
            self.data.update_attribute("action")
            if self.data.action is not None:
                action = self.data.action
                for key in ["left", "up", "right", "left"]:
                    if (
                        key not in action.forced_key_releases
                        and key in action.keys_held
                    ):
                        action.forced_key_releases.append(key)
                print(action)
                self.pipe.send(
                    ActionRequest(
                        f"{self} - Returning to Safe Spot",
                        self.data.action.send,
                        ign=self.data.ign,
                        callbacks=[self.lock.release],
                        priority=priorities.MULE_POSITIONING,
                        block_lower_priority=True,
                        log=True,
                    )
                )
            else:
                self.lock.release()
                await asyncio.sleep(1)
        logger.log(LOG_LEVEL, f"{self.data.ign} is back at safe spot.")
