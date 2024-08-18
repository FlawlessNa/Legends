import logging
import multiprocessing.connection
import multiprocessing.managers

from royals.actions import ensure_minimap_displayed
from botting import PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.WARNING


class MinimapAttributesMixin:
    data: BotData
    metadata: multiprocessing.managers.DictProxy
    pipe: multiprocessing.connection.Connection
    MINIMAP_POS_REFRESH_RATE = 0.1
    ERROR_HANDLING_TIME_LIMIT = 5.0

    def _get_minimap_pos(self) -> tuple[int, int]:
        return self.data.current_minimap.get_character_positions(
            self.data.handle,
            client_img=self.data.current_client_img,
            map_area_box=self.data.current_minimap_area_box
        ).pop()

    def _minimap_pos_error_handler(self) -> None:
        """
        Blocks the current Bot (& Engine) until the current_minimap_position the handler
        had time to attempt fixing the issue uninterrupted by other tasks.
        :return:
        """
        identifier = f'{self}.current_minimap_position Error Handler'
        logger.warning(f'{identifier} Attempt')
        lock = DecisionMaker.request_proxy(
            self.metadata,
            identifier,
            'Lock',
        )
        with lock:
            print('Lock acquired')
            print('Requesting ensure minimap from process',
                  multiprocessing.current_process().name)
            self.pipe.send(
                ActionRequest(
                    identifier,
                    ensure_minimap_displayed,
                    self.data.ign,
                    priority=20,
                    block_lower_priority=True,
                    callbacks=[lock.release],
                    args=(
                        self.data.handle, self.data.ign, self.data.current_minimap, lock
                    )
                )
            )
            print('Pipe signal Sent')
            if not lock.acquire(timeout=self.ERROR_HANDLING_TIME_LIMIT):
                breakpoint()
            else:
                print('Lock re-acquired')
                breakpoint()
            print('Out of if/else')
            breakpoint()

    def _create_minimap_attributes(self) -> None:
        self.data.create_attribute(
            "minimap_currently_displayed",
            lambda: self.data.current_minimap.is_displayed(
                self.data.handle,
                self.data.current_client_img
            ),
        )
        self.data.create_attribute(
            "current_minimap_state",
            lambda: self.data.current_minimap.get_minimap_state(
                self.data.handle,
                self.data.current_client_img
            ),
        )
        self.data.create_attribute(
            "current_minimap_area_box",
            lambda: self.data.current_minimap.get_map_area_box(self.data.handle),
        )
        self.data.create_attribute(
            "current_minimap_position",
            self._get_minimap_pos,
            threshold=self.MINIMAP_POS_REFRESH_RATE,
            error_handler=self._minimap_pos_error_handler
        )
        self.data.create_attribute(
            "current_entire_minimap_box",
            lambda: self.data.current_minimap.get_entire_minimap_box(self.data.handle),
        )
