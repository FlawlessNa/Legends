"""
The game client: what it shows, and the keys its chat takes. Its window's
handle is the generic Bot's, `botting.core.HANDLE`.
"""

from typing import Any

from botting.core import HANDLE, Key, Provider
from botting.screen import Frame, frame_source


class ClientProvider(Provider):
    """
    Serves `FRAME`, the Bot's one capture of its client, and `CHAT_KEYS`.

    The readers take the `Frame`, mob and character detection its pixels.
    `FRAME` refreshes on read once `FRAME_REFRESH` has passed; a DecisionMaker
    that must see the client as it is now refreshes it (`refresh`).

    Bot-level: the Bot reads the chat keys when it is built, so a malformed
    binding refuses the start. `setup()` captures the first frame.
    """

    bot_level = True
    needs = (HANDLE,)

    #: Seconds a frame is served before a read captures the next one.
    FRAME_REFRESH = 0.1

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        chat_keys: dict[str, str],
        **settings: object,
    ) -> None:
        """
        :param chat_keys: Every chat channel's key (`startup_chat_keys`).
        """
        super().__init__(*args, **settings)
        self.chat_keys = chat_keys

    def setup(self) -> None:
        self.register(FRAME, self._grab, threshold=self.FRAME_REFRESH)
        self.register(CHAT_KEYS, lambda: self.chat_keys)

    def _grab(self) -> Frame:
        return frame_source().grab(self.read(HANDLE))


#: What the client shows: the Bot's one capture.
FRAME: Key[Frame] = Key("frame", ClientProvider, legacy_name="current_frame")
#: Every chat channel's key, read once from the keybindings at start.
CHAT_KEYS: Key[dict[str, str]] = Key("chat_keys", ClientProvider)
