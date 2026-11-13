import functools
import logging
import multiprocessing.connection
import multiprocessing.managers
import time

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from maple.screen.position import feet_of_marker, marker_of_feet
from maple.telemetry_events import MOVEMENT_PLAN_STARTED, plan_started_payload

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
        # No `self._teleport_skill` attribute: it would shadow
        # `MovementsMixin._teleport_skill()`, which `_new_handler` calls below.
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

    async def task(self) -> None:
        self._restart_recovery_grace_period()
        await super().task()

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
                self._emit_plan_started()
                self.send(self._request())
            else:
                self.lock.release()

    def _emit_plan_started(self) -> None:
        """
        Record the Movement Plan about to be sent, from cached values only.
        `data.<name>` can re-run a thresholded update function (a fresh minimap
        read) on the send path, which would delay the Action and could run recovery
        from inside telemetry. The cache is also what the Plan was computed from.
        """
        last_known = functools.partial(self.data.get_last_known_value, update=False)
        reading = last_known("current_position")
        target = last_known("next_target")
        transform = self._world_map().minimap
        if reading is None or reading.value is None or target is None:
            return
        assert transform is not None
        virtual_position = (reading.value.x, reading.value.y)
        # From the one target read above, converted as `_virtual_target` converts
        # it, so `target_*` and `target_v*` can't describe two targets.
        virtual_target = feet_of_marker(transform, (target[0], target[1]))
        self.emit(
            MOVEMENT_PLAN_STARTED,
            plan_started_payload(
                last_known("movements"),
                marker_of_feet(transform, virtual_position),
                target,
                virtual_position=virtual_position,
                virtual_target=virtual_target,
                scale=transform.scale,
            ),
        )

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
