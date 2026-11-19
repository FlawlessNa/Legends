"""
The quick slots: what each holds, and how many. The consumables read them.
"""

from botting.core import Key, Provider, StartupRefused
from botting.screen import Reading
from maple.screen.quick_slots import QuickSlots, QuickSlotsReader

from .client import FRAME
from .screen_readers import QUICK_SLOTS_READER


class QuickSlotsProvider(Provider):
    """
    Serves `QUICK_SLOTS_READING`, read from the latest frame by the Bot's one
    quick slots reader.

    It is read once at setup, then only when a consumer refreshes it, as
    `STATUS_BAR_READING` is: `FRAME`, then `QUICK_SLOTS_READING`.
    """

    needs = (FRAME, QUICK_SLOTS_READER)

    def setup(self) -> None:
        """
        :raises StartupRefused: the Bot has no quick slots reader: no
            DecisionMaker names `QUICK_SLOTS` in its `screen_readers`.
        """
        reader = self.read(QUICK_SLOTS_READER)
        if reader is None:
            raise StartupRefused(
                f"{self} has no quick slots reader: name QUICK_SLOTS in the "
                "screen_readers of the DecisionMaker that reads the quick slots."
            )
        self.register(QUICK_SLOTS_READING, lambda: self._read(reader))

    def _read(self, reader: QuickSlotsReader) -> Reading[QuickSlots]:
        return reader.read(self.read(FRAME))


#: The quick slots, read from the latest frame. Never refreshed on its own.
QUICK_SLOTS_READING: Key[Reading[QuickSlots]] = Key("quick_slots", QuickSlotsProvider)
