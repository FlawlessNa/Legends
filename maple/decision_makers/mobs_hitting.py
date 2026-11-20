import asyncio
import functools
import logging
import math
import multiprocessing.connection
import multiprocessing.managers
import time
from collections.abc import Callable, Sequence
from typing import Any

from botting import PARENT_LOG, controller
from botting.core import (
    ActionRequest,
    BotData,
    DecisionMaker,
    StartupRefused,
    TurnGate,
    action_name,
)
from maple.actions.skills_related_v2 import cast_skill_compiler
from maple.screen.chat import CHAT, ChatReader
from maple.screen.minimap import MINIMAP
from maple.screen.name_tag import NAME_TAGS
from maple.screen.position.camera import play_area_size
from maple.telemetry_events import (
    COMBAT_MOBS_HIT,
    COMBAT_PARTIAL_REACH,
    FeetAnchor,
    MobOffset,
    MobsHitPayload,
    PartialReachPayload,
)

from .attack_choice import ClientBox, Placement, choose, partial, placement
from .mob_detection import get_mobs_positions_in_img
from .providers import (
    ATTACKS,
    CHAT_READER,
    FACING,
    FRAME,
    HANDLE,
    MOBS,
    ON_SCREEN_POSITION,
    POSITION,
    WORLD_MAP,
    Attack,
)
from .rotation import Rotation

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

#: Seconds between two `combat.partial_reach` events, at least.
PARTIAL_REACH_EVERY = 1.0


class MobsHitting(DecisionMaker):
    """
    Casts the first of the profile's `attacks` with at least its `min_mobs` in
    reach, facing as `facing` says, cancelling the rotation's movement for the
    cast (spec #631 § 6).

    One cast at a time, through its gate: a decision waits for the gate, checks
    the ladder, detects the mobs once on one frame, goes down the attacks, then
    sends the cast, whose callback leaves the gate from Main Process once the
    cast is done. A decision that sends nothing leaves it itself.
    """

    screen_readers = (MINIMAP, CHAT, NAME_TAGS)
    reads = (
        HANDLE,
        ATTACKS,
        FACING,
        FRAME,
        MOBS,
        CHAT_READER,
        WORLD_MAP,
        ON_SCREEN_POSITION,
    )
    #: The ladder check takes the position the rotation read last, never reads one.
    observes = (POSITION,)
    cancels = (Rotation,)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        clock: Callable[[], float] = time.monotonic,
        **kwargs: object,
    ) -> None:
        """
        :param clock: Seconds, monotonic: spaces the `combat.partial_reach`
            events.
        """
        super().__init__(metadata, data, pipe)
        #: The profile's attacks, in order. Set by `setup()`.
        self.attacks: tuple[Attack, ...]
        #: Its turn on the client. Made by `setup()`.
        self.gate: TurnGate
        self._clock = clock
        #: When `combat.partial_reach` was last emitted.
        self._partial_at = -math.inf
        #: Whether a client size with no known play area was logged: once per
        #: Session.
        self._no_play_area_logged = False

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no chat reader, which places the
            chat a reach stops at; or the profile has no `attacks`.
        """
        if self.read(CHAT_READER) is None:
            raise StartupRefused(f"{self} reaches down to the chat, and has no reader.")
        attacks = self.read(ATTACKS)
        if attacks is None:
            raise StartupRefused(
                f"{self} casts the profile's attacks, and it has none: list them "
                "in `attacks`, each a skill and its min_mobs, such as "
                "`attacks: [{skill: Power Strike, min_mobs: 1}]`."
            )
        self.attacks = attacks
        self.gate = TurnGate(self._proxies.instance(repr(self), "Lock"))

    def on_start(self) -> None:
        # Ensures the gate is actually free before the loop starts, no matter
        # what: a run cancelled while holding it would otherwise leave it held.
        self.gate.reset()

    def _hit_mobs(self, attack: Attack, direction: str | None) -> ActionRequest:
        """
        Builds the Action that casts `attack` at the mobs on screen.

        `direction` is the facing the cast is preluded with: the chosen side for
        a one-sided attack, None for a two-sided one.
        """
        compiler = functools.partial(
            cast_skill_compiler,
            handle=self.read(HANDLE),
            ign=self.data.ign,
            skill=attack.skill,
            direction=direction,
            # The key records of the cast carry this decision's id (#538).
            correlation_id=self.correlation_id,
        )
        return self._cast_request(compiler, attack.skill.animation_time)

    def _cast_request(self, compiler: Callable, cast_time: float) -> ActionRequest:
        """
        Wraps a dispatch-time compiler into the Action this DecisionMaker sends.

        The Action's priority, cancellation and gate handling are defined here, in
        exactly one place, whatever compiler it is handed.

        The sequence `cast_skill` builds runs for the skill's cast time by
        construction, plus a short direction prelude - so the cap is known here,
        without compiling. Doubled, as it was when it read the compiled duration.
        """
        timeout = 2 * cast_time + 1.0

        return ActionRequest(
            f"{self}",
            self._cap_duration,
            ign=self.data.ign,
            priority=2,
            cancel_tasks=[action_name(Rotation, self.data.ign)],
            block_lower_priority=True,
            callbacks=[self.gate.releaser],
            # cancels_itself=True,
            args=(self.read(HANDLE), compiler, timeout),
        )

    @staticmethod
    async def _cap_duration(
        handle: int, compiler: Callable[..., Any], timeout: float
    ) -> None:
        """
        Compiles the cast at dispatch (so it sees this client's held keys, read from
        the Held-Keys Ledger inside the focus lock) and caps how long it may run.
        """
        try:
            await asyncio.wait_for(
                controller.compile_and_send(handle, compiler), timeout=timeout
            )
        except TimeoutError:
            logger.error(
                "Skill cast on handle %s exceeded its %.2fs cap and was cancelled.",
                handle,
                timeout,
            )

    def _chat_top(self) -> int:
        """
        Where the chat starts, in client pixels: mobs under it are out of
        reach. The frame's bottom when the chat isn't found whole, so nothing is
        left out on a guess.
        """
        frame = self.read(FRAME)
        region = self._chat_reader().region(frame)
        return frame.pixels.shape[0] if region is None else region.top

    def _chat_reader(self) -> ChatReader:
        reader = self.read(CHAT_READER)
        assert reader is not None, "setup() refuses a Bot without one"
        return reader

    def _currently_on_ladder(self) -> bool:
        """
        Whether the character is on a rope or a ladder of the bot's `WorldMap`,
        where no skill is cast. An unsure position, or no map, isn't: the cast
        is tried, as it was when the position was on no feature.
        """
        world_map = self.read(WORLD_MAP)
        # The last read, without reading: the rotation reads it every cycle,
        # and a read here would cost a camera match per cast.
        reading = self.peek(POSITION)
        if world_map is None or reading is None or reading.value is None:
            return False
        return world_map.rope_at((reading.value.x, reading.value.y)) is not None

    def _placement(
        self, on_screen_pos: Sequence[int], client_size: tuple[int, int]
    ) -> Placement | None:
        """
        Where a reach goes on this frame; None, logged once per Session, when
        the client's size has no known play area to scale it by.
        """
        play_area = play_area_size(client_size)
        if play_area is None:
            if not self._no_play_area_logged:
                self._no_play_area_logged = True
                logger.warning(
                    "%s casts nothing: a client of %s has no known play area, so "
                    "no reach can be placed on it (camera.PLAY_AREAS).",
                    self,
                    client_size,
                )
            return None
        return placement(on_screen_pos, client_size, play_area, self._chat_top())

    def _report_partial(
        self,
        mobs: list[ClientBox],
        where: Placement,
        origin: tuple[int, int],
    ) -> None:
        """
        `combat.partial_reach`, at most once every `PARTIAL_REACH_EVERY`, when a
        mob is in one of a weapon-based attack's swings and out of its reach.
        """
        now = self._clock()
        if now - self._partial_at < PARTIAL_REACH_EVERY:
            return
        found = partial(self.attacks, mobs, where)
        if found is None:
            return
        attack, skipped = found
        self._partial_at = now
        payload: PartialReachPayload = {
            "attack": attack.skill.name,
            "mobs": [_offset(where, mob) for mob in skipped],
            **_anchor(where, origin),
        }
        self.emit(COMBAT_PARTIAL_REACH, payload)

    async def _decide(self) -> None:
        """
        Waits for the gate and skips a rope or a ladder. Then, on one frame,
        detects the mobs once and casts the first attack with at least its
        `min_mobs` in reach on a side, facing as `facing` says.
        """
        await self.gate.enter()
        if self._currently_on_ladder():
            await self.gate.leave()
            return

        # The box read now, or the last one found when this read finds none.
        on_screen_pos = self.read(ON_SCREEN_POSITION) or self.peek(ON_SCREEN_POSITION)
        if on_screen_pos:
            # One frame for the whole decision: the reach and the detections
            # are of the same pixels.
            frame = self.read(FRAME)
            where = self._placement(on_screen_pos, frame.client_size)
            if where is not None:
                mobs = [
                    _client_box(mob)
                    for mob in get_mobs_positions_in_img(
                        frame.pixels, self.read(MOBS), self.read(HANDLE)
                    )
                ]
                choice = choose(self.attacks, mobs, where, self.read(FACING))
                if choice is not None:
                    hit: MobsHitPayload = {
                        "mob_count": len(choice.mobs),
                        "direction": choice.direction,
                        "attack": choice.attack.skill.name,
                        "mobs": [_offset(where, mob) for mob in choice.mobs],
                        **_anchor(where, frame.origin),
                    }
                    self.emit(COMBAT_MOBS_HIT, hit)
                    self.send(self._hit_mobs(choice.attack, choice.direction))
                    return
                self._report_partial(mobs, where, frame.origin)
        await self.gate.leave()


def _client_box(mob: Sequence[int]) -> ClientBox:
    """A detection's `x1, y1, x2, y2` as ints: numpy's are converted here."""
    x1, y1, x2, y2 = mob
    return int(x1), int(y1), int(x2), int(y2)


def _anchor(where: Placement, origin: tuple[int, int]) -> FeetAnchor:
    """Where the offsets are from, on the screen (#640)."""
    return {
        "feet_x": round(where.feet[0], 1),
        "feet_y": round(where.feet[1], 1),
        "client_left": origin[0],
        "client_top": origin[1],
    }


def _offset(where: Placement, mob: ClientBox) -> MobOffset:
    left, top, right, bottom = where.offset(mob)
    return {"left": left, "top": top, "right": right, "bottom": bottom}
