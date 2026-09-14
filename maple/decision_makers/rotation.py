import logging
import multiprocessing.connection
import multiprocessing.managers
import time

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker

from .mixins import (
    MinimapAttributesMixin,
    MobsHittingMixin,
    MovementRecoveryMixin,
    MovementsMixin,
    NextTargetMixin,
)

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class Rotation(
    MovementRecoveryMixin,
    MinimapAttributesMixin,
    MovementsMixin,
    NextTargetMixin,
    MobsHittingMixin,
    DecisionMaker,
):
    """
    The rotation loop: pick a target, compute a Path, ship the Movement Plan.

    Stuck detection and reaction are `MovementRecoveryMixin`'s (`CONTEXT.md` ->
    **Movement recovery**), which replaced `FailsafeMixin`'s six raw-equality
    sentinels. Those watched two `BotData` attributes for having not *changed* in
    N seconds, which was wrong in both directions: a character casting in place
    for 30s tripped them, and a character pinned at a wall while mob knockback
    jittered its coordinates never did. The Delivery Gate fixes the first by
    construction and the jitter bound fixes the second.
    """

    _throttle = 0.1

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        movements_duration: float = 1.0,
        disable_teleport: bool = False,
        smart_rotation_enabled: bool = False,
        mob_count_threshold: int | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._teleport_skill = self.data.character.skills.get("Teleport")
        self.lock = self._proxies.instance(repr(self), "Lock")

        if disable_teleport:
            self.data.character.skills.pop("Teleport", None)

        # Minimap attributes
        self._create_minimap_attributes()

        # Rotation attributes
        self._create_rotation_attributes(
            smart_rotation=smart_rotation_enabled,
            mob_count_threshold=mob_count_threshold,
        )
        self._create_pathing_attributes(movements_duration)

        # Movement recovery
        self._create_recovery_attributes()

    async def task(self, *args: object, **kwargs: object) -> None:
        self._restart_recovery_grace_period()
        await super().task(*args, **kwargs)

    async def _decide(self) -> None:
        # Every cycle, before the lock is contended for: a cycle that cannot
        # acquire the lock is a cycle the loop spent waiting its turn, and the
        # Delivery Gate is what makes those cost nothing rather than needing to
        # be skipped here.
        self._recovery_check(time.perf_counter())

        # Only send standard request when lock is acquired, otherwise wait for lock
        if self.lock.acquire(blocking=False):
            logger.debug("%s is deciding.", self)
            self.data.update_attribute("next_target")
            self.data.update_attribute("movements")
            if self._has_movements():
                self.send(self._request())
            else:
                self.lock.release()

    def _request(self) -> ActionRequest:
        # TODO - Could switch to requeue=False while ensuring that the lock is released.
        # This is because Telecasting will move the character, and the next action should
        # be based on the new position.
        return ActionRequest(
            f"{self}",
            controller.compile_and_send,
            ign=self.data.ign,
            requeue_if_not_scheduled=False,
            callbacks=[self.lock.release],
            # The Delivery Gate's input: `compile_and_send` returns the number of
            # Steps that actually reached the client, and only a task that ran to
            # completion reports at all. See `MovementRecoveryMixin`.
            result_callbacks=[self._delivery.put_nowait],
            args=(self.data.handle, self._movement_compiler()),
        )
