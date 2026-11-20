import logging
import multiprocessing.connection
import multiprocessing.managers
import time

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker, TurnGate
from maple.model.world import WorldMap
from maple.screen.minimap import MINIMAP
from maple.screen.position import marker_of_feet
from maple.telemetry_events import MOVEMENT_PLAN_STARTED, plan_started_payload

from .providers import (
    DESTINATION,
    HANDLE,
    MOVEMENTS,
    POSITION,
    WORLD_MAP,
    PathingProvider,
    actionable,
    pathing,
)
from .recovery import ESCALATION_TARGETS, MovementRecovery, escalation_classes

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class Rotation(DecisionMaker):
    """
    The rotation loop: refresh the destination and its Movement Plan, ship the
    plan.

    Where it heads is `DESTINATION` (`DestinationProvider`), and the Path and
    its Movement Plan are `PathingProvider`'s, configured from the profile
    (`movements_duration`, `disable_teleport`). One Movement Action at a time,
    through its Turn Gate: the Action's callback leaves it from Main Process.

    Stuck detection and reaction are `MovementRecovery`'s (`CONTEXT.md` ->
    **Movement recovery**), which replaced `FailsafeMixin`'s six raw-equality
    sentinels. Those watched two `BotData` attributes for having not *changed* in
    N seconds, which was wrong in both directions: a character casting in place
    for 30s tripped them, and a character pinned at a wall while mob knockback
    jittered its coordinates never did. The Delivery Gate fixes the first by
    construction and the jitter bound fixes the second.
    """

    screen_readers = (MINIMAP,)
    reads = (
        HANDLE,
        WORLD_MAP,
        POSITION,
        DESTINATION,
        MOVEMENTS,
        *MovementRecovery.reads,
    )
    #: What an Escalate stops until a human resumes, itself included.
    pauses = ESCALATION_TARGETS
    #: A recovery rung preempts its own Movement Action.
    cancels = ("maple.decision_makers.rotation.Rotation",)

    _throttle = 0.1

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        """
        :param kwargs: The profile's settings. `movements_duration` and
            `disable_teleport` configure `PathingProvider`, and
            `smart_rotation_enabled` and `mob_count_threshold`
            `DestinationProvider`: none is read here.
        """
        super().__init__(metadata, data, pipe)
        self._recovery = MovementRecovery(self, physics=lambda: self._pathing.physics())
        #: Its turn on the client. Made by `setup()`.
        self.gate: TurnGate
        #: The Bot's pathing, for the compile and the physics. Set by `setup()`.
        self._pathing: PathingProvider

    def setup(self) -> None:
        self.gate = TurnGate(self._proxies.instance(repr(self), "Lock"))
        self._pathing = pathing(self.data)
        self._recovery.setup(self._proxies, escalation_classes())

    def on_start(self) -> None:
        self._recovery.restart_grace_period()

    async def _decide(self) -> None:
        # Every cycle, before the gate is tried: a cycle that cannot enter it is
        # a cycle the loop spent waiting its turn, and the Delivery Gate is what
        # makes those cost nothing rather than needing to be skipped here.
        self._recovery.check(time.perf_counter())

        # Only send a Movement Action on its turn: otherwise wait for the gate.
        if self.gate.try_enter():
            logger.debug("%s is deciding.", self)
            self.refresh(DESTINATION)
            self.refresh(MOVEMENTS)
            if self._has_movements():
                self._emit_plan_started()
                self.send(self._request())
            else:
                self.gate.leave_now()

    def _has_movements(self) -> bool:
        """Whether the current Movement Plan compiles to anything (`actionable`)."""
        return actionable(self.read(MOVEMENTS))

    def _world_map(self) -> WorldMap:
        world_map = self.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            raise ValueError(
                "no map to plan on: the bot's map isn't known, or has no minimap"
            )
        return world_map

    def _emit_plan_started(self) -> None:
        """
        Record the Movement Plan about to be sent, from cached values only.
        `read` can re-run a thresholded update function (a fresh minimap read)
        on the send path, which would delay the Action and could run recovery
        from inside telemetry. The cache is also what the Plan was computed from.
        """
        reading = self.peek(POSITION)
        target = self.peek(DESTINATION)
        transform = self._world_map().minimap
        if reading is None or reading.value is None or target is None:
            return
        assert transform is not None
        virtual_position = (reading.value.x, reading.value.y)
        # The target is virtual (#398); the canvas fields are where the minimap
        # draws the marker for it, from the one read above, so `target_*` and
        # `target_v*` can't describe two targets.
        virtual_target = (float(target[0]), float(target[1]))
        self.emit(
            MOVEMENT_PLAN_STARTED,
            plan_started_payload(
                self.peek(MOVEMENTS) or (),
                marker_of_feet(transform, virtual_position),
                marker_of_feet(transform, virtual_target),
                virtual_position=virtual_position,
                virtual_target=virtual_target,
                scale=transform.scale,
            ),
        )

    def _request(self) -> ActionRequest:
        # TODO - Could switch to requeue=False while ensuring that the gate is left.
        return ActionRequest(
            f"{self}",
            controller.compile_and_send,
            ign=self.data.ign,
            requeue_if_not_scheduled=False,
            callbacks=[self.gate.releaser],
            # The Delivery Gate's input: `compile_and_send` returns the number of
            # Steps that actually reached the client, and only a task that ran to
            # completion reports at all. See `MovementRecovery`.
            result_callbacks=[self._recovery.delivered],
            args=(self.read(HANDLE), self._pathing.compiler(self.correlation_id)),
        )
