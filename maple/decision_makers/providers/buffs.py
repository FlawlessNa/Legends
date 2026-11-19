"""
The buffs the profile casts, as their icons show them. `SoloRebuff` judges its
casts on them.
"""

from botting.core import Key, Provider, StartupRefused
from botting.screen import Reading
from maple.screen.buffs import BuffsReader, BuffState

from .character import BUFF_NAMES
from .client import FRAME
from .screen_readers import BUFFS_READER


class BuffsProvider(Provider):
    """
    Serves `BUFFS_READING`: the profile's buffs (`BUFF_NAMES`), read from the
    latest frame by the Bot's one buffs reader.

    It is read once at setup, then only when a consumer refreshes it: a cast is
    judged on a frame captured now, so the consumer refreshes `FRAME`, then
    `BUFFS_READING`.
    """

    needs = (FRAME, BUFFS_READER, BUFF_NAMES)

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no buffs reader: no DecisionMaker
            names `BUFFS` in its `screen_readers`.
        """
        reader = self._reader()
        names = tuple(self.read(BUFF_NAMES))
        self.register(BUFFS_READING, lambda: reader.read(self.read(FRAME), names))

    def _reader(self) -> BuffsReader:
        reader = self.read(BUFFS_READER)
        if reader is None:
            raise StartupRefused(
                f"{self} has no buffs reader: name BUFFS in the screen_readers of "
                "the DecisionMaker that reads the buffs."
            )
        return reader


#: The profile's buffs, read from the latest frame. Never refreshed on its own.
BUFFS_READING: Key[Reading[dict[str, BuffState]]] = Key("buffs", BuffsProvider)
