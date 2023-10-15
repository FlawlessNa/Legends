import asyncio
import logging

from abc import ABC

from .controls import Controller

logger = logging.getLogger(__name__)


class Bot(ABC):
    all_bots: list = []

    def __init__(self, handle, ign) -> None:
        # self._validation_keybindings(*args, **kwargs)
        self.ign = ign
        self.controller = Controller(handle=handle, ign=ign)

    # @abstractmethod
    def required_keybindings(self):
        pass

    def __repr__(self) -> str:
        return f"Bot({self.__class__.__name__})--({self.ign})"

    def _validation_keybindings(self, user_defined_keybindings) -> None:
        assert all(
            key in self.required_keybindings() for key in user_defined_keybindings
        ), f"Missing keybindings.\nRequired:\n{self.required_keybindings()}\nProvided:\n{user_defined_keybindings}."

    async def run(self) -> None:
        await self.controller.move("left", 10, True)
        logger.info(f"{self.__class__.__name__} has finished running.")

    @staticmethod
    def cancel_all_bots():
        for task in asyncio.all_tasks():
            if task.get_name().startswith("Bot"):
                task.cancel()
