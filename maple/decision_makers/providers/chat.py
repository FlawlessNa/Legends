"""
The chat: its new lines, which `ChatReplies` follows, and whether its log is
shown, which `CheckMobsStillSpawn` toggles it by.
"""

from botting.core import Key, Provider, StartupRefused
from botting.screen import Reading
from maple.screen.chat import ChatLine, ChatReader

from .client import FRAME
from .screen_readers import CHAT_READER


class ChatProvider(Provider):
    """
    Serves `CHAT_LINES` and `CHAT_SHOWN`, read from the latest frame by the
    Bot's one chat reader.

    Neither is read at setup, nor ever refreshed on its own: a consumer
    refreshes `FRAME`, then the key. Each refresh of `CHAT_LINES` returns only
    the lines new since the one before, so one DecisionMaker reads them.
    """

    needs = (FRAME, CHAT_READER)

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no chat reader: no DecisionMaker
            names `CHAT` in its `screen_readers`.
        """
        reader = self.read(CHAT_READER)
        if reader is None:
            raise StartupRefused(
                f"{self} has no chat reader: name CHAT in the screen_readers of "
                "the DecisionMaker that reads the chat."
            )
        self.register(
            CHAT_LINES,
            lambda: self._lines(reader),
            initial_value=Reading.absent(0.0, "not read yet"),
        )
        self.register(
            CHAT_SHOWN,
            lambda: self._shown(reader),
            initial_value=Reading.absent(0.0, "not read yet"),
        )

    def _lines(self, reader: ChatReader) -> Reading[list[ChatLine]]:
        return reader.read(self.read(FRAME))

    def _shown(self, reader: ChatReader) -> Reading[bool]:
        return reader.shown(self.read(FRAME))


#: The chat lines new since the last refresh, top to bottom, each with its
#: `text`, `speaker`, `message` and `outgoing`. `ABSENT` until the first
#: refresh, which returns every line shown. Never refreshed on its own.
CHAT_LINES: Key[Reading[list[ChatLine]]] = Key("chat_lines", ChatProvider)
#: Whether the chat log is shown: `COVERED` or an unusable frame when that
#: can't be told. Never refreshed on its own.
CHAT_SHOWN: Key[Reading[bool]] = Key("chat_shown", ChatProvider)
