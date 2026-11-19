import asyncio
import functools
import logging
import multiprocessing.connection
import multiprocessing.managers
from collections.abc import Callable
from typing import Any

import numpy as np

from botting import PARENT_LOG, controller
from botting.core import (
    ActionRequest,
    BotData,
    DecisionMaker,
    StartupRefused,
    TurnGate,
    action_name,
)
from botting.utilities import Box
from maple.actions.skills_related_v2 import cast_skill_compiler
from maple.model.characters import MapleSkill
from maple.screen.chat import CHAT, ChatReader
from maple.screen.minimap import MINIMAP
from maple.screen.name_tag import NAME_TAGS
from maple.telemetry_events import COMBAT_MOBS_HIT, MobsHitPayload

from .mob_detection import (
    box_center,
    get_closest_mob_direction,
    get_mobs_positions_in_img,
    mob_count_in_img,
)
from .providers import (
    CHARACTER,
    CHAT_READER,
    FRAME,
    HANDLE,
    MOBS,
    ON_SCREEN_POSITION,
    POSITION,
    WORLD_MAP,
)
from .rotation import Rotation

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MobsHitting(DecisionMaker):
    """
    Casts the training skill once enough mobs are in its reach, cancelling the
    rotation's movement for the cast.

    One cast at a time, through its gate: a decision waits for the gate, checks
    the ladder, counts the mobs, then sends the cast, whose callback leaves the
    gate from Main Process once the cast is done. A decision that sends nothing
    leaves it itself.
    """

    screen_readers = (MINIMAP, CHAT, NAME_TAGS)
    reads = (
        HANDLE,
        CHARACTER,
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
        mob_count_threshold: int,
        training_skill: str | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self.mob_threshold = mob_count_threshold
        self._training_skill_name = training_skill
        #: The skill it casts. Set by `setup()`.
        self.training_skill: MapleSkill
        #: Its turn on the client. Made by `setup()`.
        self.gate: TurnGate

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no chat reader, which places the
            chat the skill's reach stops at.
        """
        if self.read(CHAT_READER) is None:
            raise StartupRefused(f"{self} reaches down to the chat, and has no reader.")
        self.training_skill = self._get_skill_from_str(self._training_skill_name)
        self.gate = TurnGate(self._proxies.instance(repr(self), "Lock"))

    def on_start(self) -> None:
        # Ensures the gate is actually free before the loop starts, no matter
        # what: a run cancelled while holding it would otherwise leave it held.
        self.gate.reset()

    def _hit_mobs(self, direction: str | None) -> ActionRequest:
        """
        Builds the Action that casts the training skill at the mobs on screen.

        `direction` is the facing the cast is preluded with - set by `_decide` for a
        unidirectional skill, None for one that hits both ways.
        """
        compiler = functools.partial(
            cast_skill_compiler,
            handle=self.read(HANDLE),
            ign=self.data.ign,
            skill=self.training_skill,
            direction=direction,
            # The key records of the cast carry this decision's id (#538).
            correlation_id=self.correlation_id,
        )
        return self._cast_request(compiler)

    def _cast_request(self, compiler: Callable) -> ActionRequest:
        """
        Wraps a dispatch-time compiler into the Action this DecisionMaker sends.

        The seam subclasses swap: `TelecastMobsHitting` fuses the same cast into a
        movement and hands the fused compiler here, so the Action's priority,
        cancellation and gate handling stay defined in exactly one place.

        The sequence `cast_skill` builds runs for the skill's animation time by
        construction, plus a short direction prelude - so the cap is known here,
        without compiling. Doubled, as it was when it read the compiled duration.
        The same cap covers a telecast: `telecast` truncates its rebuilt sequence to
        that very animation time. The cut lands on a paired-press boundary, so it can
        overshoot by up to one teleport animation - still well inside the doubled cap.
        """
        timeout = 2 * self.training_skill.animation_time + 1.0

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

    def _get_skill_from_str(self, skill_str: str | None) -> MapleSkill:
        character = self.read(CHARACTER)
        if skill_str:
            return character.skills[skill_str]
        return character.skills[character.main_skill]

    def _mask_for_skill_range(
        self, pos: tuple[int, int, int, int], pixels: np.ndarray
    ) -> np.ndarray:
        horizontal = self.training_skill.horizontal_screen_range
        vertical_up = (
            self.training_skill.vertical_up_screen_range
            or self.training_skill.vertical_screen_range
        )
        vertical_down = (
            self.training_skill.vertical_down_screen_range
            or self.training_skill.vertical_screen_range
        )
        # TODO - With detection configs and no model, `Character.get_onscreen_position`
        #  still returns x, y, w, h, so `pos` is not x1, y1, x2, y2 there. Mobs are
        #  x1, y1, x2, y2 on both paths (#74). Fix for the character: #231.
        x1, _y1, x2, y2 = pos
        # x1, y1, w, h = pos
        # x2 = x1 + w
        # y2 = y1 + h
        region = Box(
            # TODO - finetune the region better? (Right now it uses smallest region)
            left=x1 - horizontal // 2,
            right=x2 + horizontal // 2,
            top=y2 - vertical_up // 2,
            bottom=min(y2 + vertical_down // 2, self._chat_top()),
        )
        mask = np.zeros(pixels.shape, np.uint8)
        mask[region.top : region.bottom, region.left : region.right] = 255
        return mask

    def _chat_top(self) -> int:
        """
        Where the chat starts, in client pixels: mobs under it are out of reach
        of the skill region. The frame's bottom when the chat isn't found whole,
        so nothing is left out on a guess.
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

    def _closest_mob_direction(
        self,
        on_screen_pos: tuple[int, int, int, int],
        pixels: np.ndarray,
        mask: np.ndarray,
    ) -> str | None:
        """
        The facing a unidirectional training skill should be cast in: towards the
        mob closest to the character.

        Detection failing here is not worth losing the cast over - the skill still
        hits, just without a facing prelude - so a failure falls back to None.
        """
        try:
            mobs_locations = get_mobs_positions_in_img(
                pixels, self.read(MOBS), self.read(HANDLE), mask=mask
            )
            return get_closest_mob_direction(box_center(on_screen_pos), mobs_locations)
        except Exception:
            logger.exception(
                "%s failed to determine the closest mob direction; casting without a "
                "facing prelude.",
                self,
            )
            return None

    async def _decide(self) -> None:
        """
        Looks for the character on-screen, or use the last known location.
        Crop the image to the region of interest, centered around character location.
        Then, count the number of mobs in the region.
        If the number of mobs is greater than the threshold, cast the skill.
        :return:
        """
        await self.gate.enter()
        if self._currently_on_ladder():
            await self.gate.leave()
            return

        # The box read now, or the last one found when this read finds none.
        on_screen_pos = self.read(ON_SCREEN_POSITION) or self.peek(ON_SCREEN_POSITION)
        closest_mob_direction = None

        if on_screen_pos:
            # One frame for the whole decision: the mask and the detections
            # must be of the same pixels.
            pixels = self.read(FRAME).pixels
            mask = self._mask_for_skill_range(on_screen_pos, pixels)
            mobs = self.read(MOBS)
            nbr_mobs = mob_count_in_img(pixels, mobs, self.read(HANDLE), mask=mask)

            if nbr_mobs >= self.mob_threshold:
                if self.training_skill.unidirectional:
                    closest_mob_direction = self._closest_mob_direction(
                        on_screen_pos, pixels, mask
                    )
                hit: MobsHitPayload = {
                    "mob_count": int(nbr_mobs),
                    "direction": closest_mob_direction,
                }
                self.emit(COMBAT_MOBS_HIT, hit)
                self.send(self._hit_mobs(closest_mob_direction))
                return
        await self.gate.leave()
