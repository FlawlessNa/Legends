import itertools
import logging

from botting.communications import BaseParser
from botting.core.action_data import ActionRequest
from botting.screen import frame_source
from maple.actions import (
    DEFAULT_CHAT_KEYS,
    chat_keys,
    priorities,
    started_chat_keys,
    write_in_chat,
)
from maple.screen.client import find_client

logger = logging.getLogger(__name__)

_WRITES = itertools.count(1)
"""Numbers each `WRITE`'s request. A `WRITE` may wait behind the line being typed
(`writing`'s chat-input guard), so the next can come while it is still running,
and two requests sharing an identifier end the Task Manager."""


class MapleParser(BaseParser):
    """
    Extends the base parser to add the following functions:
    - Kill by Returning to Lounge  # TODO
    - Kill by Logging Out / Closing all clients  # TODO
    - Write functions to General and Whisper chat channels  # TODO
    """

    def pause(self, who: list[str] | None = None) -> str:
        if who is None:
            who = ["All"]
        return f"PAUSE {' '.join(who)}"

    def resume(self, who: list[str] | None = None) -> str:
        if who is None:
            who = ["All"]
        return f"RESUME {' '.join(who)}"

    def write(
        self,
        message: str,
        who: str | None = None,
        *,
        to: str | None = None,
        channel: str | None = None,
    ) -> ActionRequest:
        assert who is not None, "BaseParser names the IGN before it calls write"
        handle = find_client()
        return ActionRequest(
            f"Writing Message received from Discord #{next(_WRITES)}",
            write_in_chat,
            who,
            priorities.USER_REQUESTS,
            block_lower_priority=True,
            args=(handle, message),
            kwargs={"keys": _chat_keys(who), **self._where(to, channel)},
            cancel_tasks=[
                f"Rotation({who})",
                f"MobsHitting({who})",
                f"TelecastMobsHitting({who})",
            ],
            callbacks=[lambda: self._confirmation_with_image(handle)],
        )

    @staticmethod
    def _where(to: str | None, channel: str | None) -> dict[str, str]:
        """The channel and whisper target `write_in_chat` is given."""
        if to is not None:
            return {"channel": "whisper", "whisper_to": to}
        # Neither given: write_in_chat's own default, exactly what a plain
        # WRITE sent before.
        return {"channel": channel} if channel else {}

    def _confirmation_with_image(self, handle: int) -> None:
        frame = frame_source().grab(handle)
        if not frame.ok:
            self.pipe.send(f"Could not capture the client: {frame.reason}")
            return
        self.pipe.send(frame.pixels)


def _chat_keys(ign: str) -> dict[str, str]:
    """
    `ign`'s chat keys, as its bot read them at startup (`started_chat_keys`).
    For an IGN no bot here started with, they are read now, or are the defaults
    when `configs/keybindings.ini` has no section for it: writing from Discord
    never needed one, and a mistyped IGN must not end the Session.
    """
    started = started_chat_keys(ign)
    if started is not None:
        return started
    try:
        return chat_keys(ign)
    except AssertionError, KeyError:
        logger.warning(
            "No keybindings section for %r: writing with the default chat keys.", ign
        )
        return dict(DEFAULT_CHAT_KEYS)
