"""
`ChatWatch`: reads the chat, and raises the alarm on a GM's line.

It sends no input: no key, no click, nothing typed. Its only request to Main
Process is a no-op Action carrying the Discord alert, sent when Discord is
configured. Nothing answers chat; that is a later topic (#302).

On MSCW, GM lines haven't been captured yet, so the chat reader reads them as
`unknown` and this alarm can't fire until their colours are in the frame set
(`maple/screen/chat.py`).
"""

import logging
import multiprocessing.connection
import multiprocessing.managers
from pathlib import Path

from botting import PARENT_LOG
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from botting.screen import Reading, Status
from maple.actions import priorities
from maple.screen.chat import CHAT, ChatKind, ChatLine
from maple.telemetry_events import CHAT_GM_LINE, ChatLinePayload
from paths import ROOT

from .mixins import UIMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

DISCORD_CONFIG = Path(ROOT) / "configs" / "discord.ini"


class ChatWatch(UIMixin, DecisionMaker):
    """Reads `chat_lines` every cycle; on each new GM line, emits
    `chat.gm_line` and, when Discord is configured, alerts with the line's image."""

    _throttle = 1.0
    screen_readers = (CHAT,)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        discord_config: Path = DISCORD_CONFIG,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._discord_config = discord_config
        self._last_status: Status | None = None
        if not self.data.has_chat_attributes:
            self._create_chat_attributes()

    async def _decide(self) -> None:
        self.data.update_attributes("current_frame", "chat_lines")
        reading: Reading[list[ChatLine]] = self.data.chat_lines
        self._log_status(reading)
        if reading.value is None:
            return
        for line in reading.value:
            if line.kind is ChatKind.GM:
                self._alarm(line)

    def _log_status(self, reading: Reading[list[ChatLine]]) -> None:
        """Log an unreadable chat once per change of status, not every cycle."""
        if reading.status is self._last_status:
            return
        self._last_status = reading.status
        if reading.status is not Status.READ:
            logger.info(
                "%s can't read the chat: %s (%s)",
                self.data.ign,
                reading.status.value,
                reading.detail,
            )

    def _alarm(self, line: ChatLine) -> None:
        logger.critical("%s sees a GM line in the chat: %r", self.data.ign, line.text)
        payload: ChatLinePayload = {
            "kind": line.kind.value,
            "text": line.text,
            "row_top": int(line.top),
        }
        self.emit(CHAT_GM_LINE, payload)
        if self._discord_config.is_file():
            message = f"{self.data.ign}: a GM line in the chat" + (
                f": {line.text}" if line.text is not None else ""
            )
            self.send(
                ActionRequest(
                    f"{self} - GM alert",
                    _noop,
                    ign=self.data.ign,
                    priority=priorities.ANTI_DETECTION,
                    cancels_itself=True,
                    discord_request=DiscordRequest(message, line.image),
                )
            )


async def _noop() -> None:
    """An Action whose whole purpose is the Discord alert riding on it."""
