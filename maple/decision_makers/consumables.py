import logging
import multiprocessing.connection
import multiprocessing.managers
import random
from abc import ABC, ABCMeta

from botting import PARENT_LOG, controller
from botting.core import ActionRequest, BotData, DecisionMaker
from maple.actions import priorities
from maple.screen.quick_slots import QUICK_SLOTS, QuickSlots
from maple.screen.status_bar import STATUS_BAR

from .providers import FRAME, HANDLE, QUICK_SLOTS_READING
from .readings import HeldReading

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class ThrottleMeta(ABCMeta):
    def __init__(
        cls, name: str, bases: tuple[type, ...], dct: dict[str, object]
    ) -> None:
        if (
            "_throttle" not in [key.lower() for key in dct]
            or dct.get("_throttle", dct["_THROTTLE"]) is None
        ):
            raise TypeError(f"Class {name} must define a '_throttle' class variable.")
        super().__init__(name, bases, dct)


class UseAndCheckConsumable(DecisionMaker, ABC, metaclass=ThrottleMeta):
    """
    Decision maker that uses a consumable every time it is called.
    It also checks for the number of remaining consumables within the QuickSlots.
    """

    # The status bar's reader stays declared, as it always was; nothing here
    # reads the status bar yet.
    screen_readers = (STATUS_BAR, QUICK_SLOTS)
    reads = (HANDLE, FRAME, QUICK_SLOTS_READING)

    _THROTTLE = 3600  # Use this to set the interval at which a consumable is taken.

    @property
    def _throttle(self) -> float:  # pyright: ignore[reportIncompatibleVariableOverride]
        # A property where the base declares a plain attribute: deliberate, so
        # that each cycle re-rolls the interval instead of every consumable of a
        # kind firing on the same tick. Read-only is enough - nothing assigns
        # `_throttle` on an instance.
        return self.__class__._THROTTLE * random.uniform(0.9, 1.1)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        keyname: str,
        num_usage: int = 1,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe)
        self._keyname = keyname
        #: The consumable's key, from the keybindings. Set by `setup()`.
        self._key = ""
        self.num_usage = num_usage
        self._quick_slots: HeldReading[QuickSlots, QuickSlots | None] = HeldReading(
            self, "quick slots", lambda slots: slots, None
        )

    def setup(self) -> None:
        """
        :raises KeyError: the character's keybindings bind no key to the
            consumable.
        """
        self._key = controller.key_binds(self.data.ign)[self._keyname]

    async def _decide(self) -> None:
        self._use_consumable()
        self._check_remaining_consumables()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.data.ign}, {self.num_usage})"

    def _use_consumable(self) -> None:
        """
        Uses the consumable.
        As a validation, we could check that the number of consumables has decreased by
        self.num_usage. # TODO
        """
        if self.num_usage > 0:
            self.send(
                ActionRequest(
                    f"{self}",
                    controller.press,
                    self.data.ign,
                    priority=priorities.FOOD,
                    args=(self.read(HANDLE), self._key),
                    kwargs={"silenced": True, "nbr_times": self.num_usage},
                )
            )

    def _check_remaining_consumables(self) -> None:
        """
        Checks the remaining consumables.

        Not built: what to do when potions run low is a later topic. The counts
        are read by `maple.screen.quick_slots`; `QuickSlots.slot(n)` resolves the
        `Quick slots` setting's numbers to them. Until then, the quick slots
        last read are kept, and a misread is only logged (`HeldReading`).
        """
        self.refresh(FRAME)
        self._quick_slots(self.refresh(QUICK_SLOTS_READING))


class PetFood(UseAndCheckConsumable):
    _THROTTLE = 720

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        num_pets: int = 1,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe, "Pet Food", num_usage=num_pets)


class MountFood(UseAndCheckConsumable):
    _THROTTLE = 720

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe, "Mount Food", num_usage=1)


class SpeedPill(UseAndCheckConsumable):
    _THROTTLE = 600

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        **kwargs: object,
    ) -> None:
        super().__init__(metadata, data, pipe, "Speed Pill", num_usage=1)
