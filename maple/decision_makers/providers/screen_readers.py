"""
The screen readers: what reads the game's interface off a `Frame`.

`MapleBot.child_init` loads the sprites the Bot's DecisionMakers declare in
their `screen_readers` (`maple.screen.sprites`) and builds a reader for each,
then `ScreenReadersProvider` with them.
"""

from typing import Any

from botting.core import Key, Provider
from maple.screen.buffs import BuffsReader
from maple.screen.chat import ChatReader
from maple.screen.locator import FrameCheck
from maple.screen.minimap import MinimapReader
from maple.screen.quick_slots import QuickSlotsReader
from maple.screen.sprites import ReaderSprites
from maple.screen.status_bar import StatusBarReader


class ScreenReadersProvider(Provider):
    """
    Serves the screen readers, and the sprites and frame check they are built
    on, each as `MapleBot.child_init` built it.

    A reader is None when no DecisionMaker of the Bot declares it in
    `screen_readers`, and so its sprites were not loaded. The frame check is
    None when no reader is.

    Bot-level: the Bot builds it, since only the Bot knows every DecisionMaker's
    `screen_readers`. `setup()` does no I/O: loading the sprites was the Bot's.
    """

    bot_level = True

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        sprites: ReaderSprites,
        frame_check: FrameCheck | None = None,
        status_bar: StatusBarReader | None = None,
        quick_slots: QuickSlotsReader | None = None,
        buffs: BuffsReader | None = None,
        minimap: MinimapReader | None = None,
        chat: ChatReader | None = None,
        **settings: object,
    ) -> None:
        """
        :param sprites: Every sprite the readers were built from.
        :param frame_check: What every reader checks a frame with first.
        :param status_bar: The status bar's reader, or None.
        :param quick_slots: The quick slots' reader, or None.
        :param buffs: The buff icons' reader, or None.
        :param minimap: The minimap's reader, or None.
        :param chat: The chat's reader, or None.
        """
        super().__init__(*args, **settings)
        self.sprites = sprites
        self.frame_check = frame_check
        self.status_bar = status_bar
        self.quick_slots = quick_slots
        self.buffs = buffs
        self.minimap = minimap
        self.chat = chat

    def setup(self) -> None:
        self.register(READER_SPRITES, lambda: self.sprites)
        self.register(FRAME_CHECK, lambda: self.frame_check)
        self.register(STATUS_BAR_READER, lambda: self.status_bar)
        self.register(QUICK_SLOTS_READER, lambda: self.quick_slots)
        self.register(BUFFS_READER, lambda: self.buffs)
        self.register(MINIMAP_READER, lambda: self.minimap)
        self.register(CHAT_READER, lambda: self.chat)


#: Every sprite the Bot's readers were built from, loaded once at start.
READER_SPRITES: Key[ReaderSprites] = Key("reader_sprites", ScreenReadersProvider)
#: What every reader checks a frame with first. None when no reader is enabled.
FRAME_CHECK: Key[FrameCheck | None] = Key("frame_check", ScreenReadersProvider)
#: The status bar's reader: level, HP, MP and EXP.
STATUS_BAR_READER: Key[StatusBarReader | None] = Key(
    "status_bar_reader", ScreenReadersProvider
)
#: The quick slots' reader: what each slot holds, and how many.
QUICK_SLOTS_READER: Key[QuickSlotsReader | None] = Key(
    "quick_slots_reader", ScreenReadersProvider
)
#: The buff icons' reader.
BUFFS_READER: Key[BuffsReader | None] = Key("buffs_reader", ScreenReadersProvider)
#: The minimap's reader. A MapleBot always declares it: it checks its map at
#: start on the minimap.
MINIMAP_READER: Key[MinimapReader | None] = Key("minimap_reader", ScreenReadersProvider)
#: The chat's reader.
CHAT_READER: Key[ChatReader | None] = Key("chat_reader", ScreenReadersProvider)
