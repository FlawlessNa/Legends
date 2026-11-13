import logging
import multiprocessing.connection
import multiprocessing.managers
import time
from collections.abc import Callable, Mapping
from functools import cached_property
from typing import Any

import win32gui

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, ProxyFactory
from botting.screen import Reading
from botting.utilities import Box
from maple.actions import ensure_minimap_displayed
from maple.screen.minimap import MINIMAP, MinimapState, MinimapView
from maple.screen.position import Fusion, PositionFusion, VirtualPosition
from maple.telemetry_events import POSITION_READ, PositionReadPayload

from ._readings import HeldReading

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MinimapAttributesMixin:
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection
    send: Callable[[ActionRequest], None]
    emit: Callable[[str, Mapping[str, Any] | None], None]
    _proxies: ProxyFactory
    MINIMAP_POS_REFRESH_RATE = 0.1
    ERROR_HANDLING_TIME_LIMIT = 7.5
    screen_readers = (MINIMAP,)

    def _read_minimap(self) -> Reading[MinimapView]:
        return self.data.minimap_reader.read(self.data.current_frame)

    def _get_minimap_pos(self) -> tuple[int, int]:
        """
        The minimap marker's canvas pixel: whether the minimap places the
        character at all, which is what `_minimap_pos_error_handler` checks
        after each attempt. No DecisionMaker positions itself by it since #398:
        `current_position` is the position, in virtual px.

        :raises ValueError: The minimap wasn't read, or the position wasn't (the
            map's canvas not found, or its marker covered).
        """
        reading: Reading[MinimapView] = self.data.minimap_reading
        if reading.value is None:
            raise ValueError(
                f"minimap {reading.status.value}: {reading.detail or 'no detail'}"
            )
        position = reading.value.self_position
        if position.value is None:
            raise ValueError(f"position {position.status.value}: {position.detail}")
        return position.value

    def _get_position(self) -> Reading[VirtualPosition]:
        """
        The character's virtual position (`PositionFusion`), from the minimap
        reading and the current frame. Every read is recorded (`position.read`),
        unsure ones included.

        **Who handles an unsure position** (#396). When the minimap gave no
        position, this raises, and `_minimap_pos_error_handler` makes the
        minimap readable again. When the minimap read is fine but fusion is
        `UNSURE` (the reads disagree, or two characters stand where the minimap
        puts ours), the `UNSURE` reading is returned: the minimap handler can't
        fix that, and a consumer holds until a read places the character
        (`MovementsMixin` plans no Path, the rotation keeps its target). A long
        streak of them is reported by movement recovery (#398).

        :raises ValueError: The minimap gave no position, or the bot has no
            position fusion (no map, or no frame check), which hands over to
            `_minimap_pos_error_handler`.
        """
        fusion: PositionFusion | None = getattr(self.data, "position_fusion", None)
        if fusion is None:
            raise ValueError("no position fusion: the bot's map isn't known")
        minimap = self.data.minimap_reading
        result = fusion.read(self.data.current_frame, minimap)
        self.emit(POSITION_READ, position_read_payload(result))
        position = result.position
        if position.value is None and result.minimap is None:
            raise ValueError(f"position {position.status.value}: {position.detail}")
        return position

    def _minimap_pos_error_handler(self) -> None:
        """
        Blocks the current Bot (& Engine) until the handler had time to make the
        minimap place the character again, uninterrupted by other tasks.
        :return:
        """
        identifier = f"{self}.current_position Error Handler"
        logger.warning("%s Attempt", identifier)
        condition = self._proxies.instance(identifier, "Condition")
        attempt = 0
        while True:
            # The cursor goes first: resting on a frame piece, it makes the minimap
            # read COVERED, and `ensure_minimap_displayed` would press the toggle
            # on an expanded minimap. The move runs during the pause below.
            self._ensure_mouse_not_on_minimap(identifier)
            time.sleep(1.5)
            ensure_minimap_displayed(
                identifier,
                self.data.handle,
                self.data.ign,
                self.pipe,
                self.data.minimap_reader,
                condition,
                self.ERROR_HANDLING_TIME_LIMIT,
            )
            logger.info("Minimap fully displayed confirmed")
            try:
                self.data.update_attributes("current_frame", "minimap_reading")
                self._get_minimap_pos()
                break
            except Exception:
                attempt += 1
                logger.error("%s Attempt %s failed", identifier, attempt)
                if attempt >= 5:
                    raise

        self.data.update_attributes(
            "current_frame",
            "minimap_reading",
            "minimap_currently_displayed",
            "current_entire_minimap_box",
        )

    def _ensure_mouse_not_on_minimap(self, identifier: str) -> None:
        """
        Looks into the current_entire_minimap_box is currently known.
        If it is, set a mouse position target that is anywhere on the window except for
        the minimap.
        If not, the target is set to the center of the window (with small variation).
        # TODO - If other mouse functions are needed, crate a maple.action module instead.
        :param identifier:
        :return:
        """
        if getattr(self.data, "current_entire_minimap_box", None) is not None:
            region_to_avoid = self.data.current_entire_minimap_box
        else:
            # In this case, avoid the first "quadrant" of the window.
            region_to_avoid = Box(left=0, right=500, top=0, bottom=500)

        # Choose a random point in the client area that is not on the minimap. Both
        # are in client pixels, which is what `controller.mouse_move` takes.
        _, _, width, height = win32gui.GetClientRect(self.data.handle)
        client_box = Box(left=0, right=width, top=0, bottom=height)
        while True:
            x, y = client_box.random()
            if (x, y) not in region_to_avoid:
                break

        request = ActionRequest(
            identifier,
            controller.mouse_move,
            self.data.ign,
            args=(self.data.handle, (x, y)),
            cancels_itself=True,
        )
        self.send(request)

    @cached_property
    def _held_minimap_shown(self) -> HeldReading[MinimapView, bool]:
        return HeldReading(
            self,
            "minimap shown",
            lambda view: view.state is MinimapState.EXPANDED,
            False,
            absent=lambda: False,
        )

    @cached_property
    def _held_minimap_bounds(self) -> HeldReading[MinimapView, Box | None]:
        return HeldReading(self, "minimap bounds", lambda view: view.bounds, None)

    def _minimap_displayed(self) -> bool:
        """
        Whether the minimap is read expanded: a minimised one shows no map, so
        no position. Not on screen is an answer (False); covered or unsure
        keeps the last answer (`HeldReading`).
        """
        return self._held_minimap_shown(self.data.minimap_reading)

    def _entire_minimap_box(self) -> Box | None:
        """
        The whole minimap, frame included, in client pixels: the last one read,
        or None before the first (`HeldReading`).
        """
        return self._held_minimap_bounds(self.data.minimap_reading)

    def _create_minimap_attributes(self) -> None:
        ensure_minimap_displayed(
            f"{self} Initial Setup",
            self.data.handle,
            self.data.ign,
            self.pipe,
            self.data.minimap_reader,
            getattr(
                self,
                "_condition",
                self._proxies.instance(f"{self} Initial Setup", "Condition"),
            ),
            self.ERROR_HANDLING_TIME_LIMIT,
        )
        self.data.create_or_reconfigure_attribute(
            "minimap_reading",
            self._read_minimap,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
        )
        self.data.create_or_reconfigure_attribute(
            "minimap_currently_displayed", self._minimap_displayed
        )
        # Refreshed with the reading it comes from, so a client resized
        # mid-session moves it too.
        self.data.create_or_reconfigure_attribute(
            "current_entire_minimap_box",
            self._entire_minimap_box,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
        )
        # The character's position, in virtual px, for every DecisionMaker
        # (#398). Not read here: the first consumer to ask reads it, and its
        # reads cost a camera match each.
        self.data.create_or_reconfigure_attribute(
            "current_position",
            self._get_position,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
            initial_value=Reading.unsure(0.0, "not read yet"),
            error_handler=self._minimap_pos_error_handler,
        )
        self.data.set_feature("has_minimap_attributes")


def position_read_payload(fusion: Fusion) -> PositionReadPayload:
    """`position.read`'s payload, from a read of the position."""
    value = fusion.position.value
    camera = fusion.camera
    minimap = fusion.minimap
    return {
        "status": fusion.position.status.value,
        "source": None if value is None else value.source.value,
        "x": None if value is None else round(float(value.x), 1),
        "y": None if value is None else round(float(value.y), 1),
        "minimap_x": None if minimap is None else int(minimap[0]),
        "minimap_y": None if minimap is None else int(minimap[1]),
        "camera_x": None if camera is None else int(camera.x),
        "camera_y": None if camera is None else int(camera.y),
        "found": len(fusion.sightings),
        "near": fusion.near,
        "by_tag": fusion.by_tag,
        "own_elsewhere": fusion.own_elsewhere,
        "detail": fusion.position.detail,
    }
