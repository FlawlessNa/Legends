"""
The status bar: level, HP, MP and EXP. A DecisionMaker reads
`STATUS_BAR_READING`; `AbilityPointDistributor` does.
"""

from botting.core import Key, Provider, StartupRefused
from botting.screen import Reading
from maple.screen.status_bar import StatusBar, StatusBarReader

from .client import FRAME
from .screen_readers import STATUS_BAR_READER


class StatusBarProvider(Provider):
    """
    Serves `STATUS_BAR_READING`, read from the latest frame by the Bot's one
    status bar reader.

    It is read once at setup, then only when a consumer refreshes it: the
    consumer refreshes `FRAME`, then `STATUS_BAR_READING`, and reads its
    `status` before its `value`. `FRAME` keeps its own threshold.
    """

    needs = (FRAME, STATUS_BAR_READER)

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no status bar reader: no
            DecisionMaker names `STATUS_BAR` in its `screen_readers`.
        """
        reader = self.read(STATUS_BAR_READER)
        if reader is None:
            raise StartupRefused(
                f"{self} has no status bar reader: name STATUS_BAR in the "
                "screen_readers of the DecisionMaker that reads the status bar."
            )
        self.register(STATUS_BAR_READING, lambda: self._read(reader))

    def _read(self, reader: StatusBarReader) -> Reading[StatusBar]:
        return reader.read(self.read(FRAME))


#: The status bar, read from the latest frame. Never refreshed on its own.
STATUS_BAR_READING: Key[Reading[StatusBar]] = Key("status_bar", StatusBarProvider)
