import asyncio
from abc import ABC

from .controller import Controller
import logging

logger = logging.getLogger(__name__)


class Bot(ABC):
    def __init__(self, handle, ign) -> None:
        # self._validation_keybindings(*args, **kwargs)
        self.controller = Controller(handle=handle, ign=ign)

    # @abstractmethod
    def required_keybindings(self):
        pass

    def _validation_keybindings(self, user_defined_keybindings) -> None:
        assert all(
            key in self.required_keybindings() for key in user_defined_keybindings
        ), f"Missing keybindings.\nRequired:\n{self.required_keybindings()}\nProvided:\n{user_defined_keybindings}."

    async def run(self) -> None:
        # await self.controller.move("left", 5, False)
        await asyncio.sleep(30)
