"""
Where the character is on screen: its box on the client, in client pixels.
"""

from botting.core import HANDLE, Key, Provider, StartupRefused
from botting.utilities import Box
from maple.screen.chat import ChatReader

from .character import CHARACTER
from .client import FRAME
from .minimap import MINIMAP_BOX
from .screen_readers import CHAT_READER


class OnScreenPositionProvider(Provider):
    """
    Serves `ON_SCREEN_POSITION`: the character found on the current frame,
    with the minimap and the chat hidden, since a character drawn there is not
    ours. `MobsHitting` created it, and sizes its skill's reach around it.
    """

    needs = (HANDLE, CHARACTER, FRAME, MINIMAP_BOX, CHAT_READER)

    #: Seconds a box is served before a read finds the character again.
    REFRESH = 0.25
    #: The detection model's acceptance threshold for the character.
    ACCEPTANCE = 0.65

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no chat reader, which hides the chat.
            A Bot that reads this key has one: `MobsHitting` declares it.
        """
        self._chat_reader()
        self.register(ON_SCREEN_POSITION, self._find, threshold=self.REFRESH)

    def _chat_reader(self) -> ChatReader:
        reader = self.read(CHAT_READER)
        if reader is None:
            raise StartupRefused(
                f"{self} has no chat reader: the Bot's sprites have no chat."
            )
        return reader

    def _find(self) -> tuple[int, int, int, int] | None:
        """
        The character's box (x1, y1, x2, y2) on the current frame, or None when
        it is not found.
        """
        return self.read(CHARACTER).get_onscreen_position(
            self.read(FRAME).pixels,
            self.read(HANDLE),
            self.regions_to_hide(),
            acceptance_threshold=self.ACCEPTANCE,
        )

    def regions_to_hide(self) -> list[Box]:
        """
        Where a character found on screen is not ours, in client pixels: the
        minimap, as `MinimapProvider` last read it, and the chat, while the chat
        reader finds it whole. A region not read yet is left out.
        """
        regions = [self.read(MINIMAP_BOX)]
        regions.append(self._chat_reader().region(self.read(FRAME)))
        return [region for region in regions if region is not None]


#: The character's box on the client (x1, y1, x2, y2), in client pixels; None
#: when the last read did not find it.
ON_SCREEN_POSITION: Key[tuple[int, int, int, int] | None] = Key(
    "on_screen_position",
    OnScreenPositionProvider,
    legacy_name="current_on_screen_position",
)
