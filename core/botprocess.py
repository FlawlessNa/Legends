import asyncio
from abc import ABC, abstractmethod
from core.controller import Controller

class BotProcess(ABC):
    def __init__(self, handle, ign) -> None:
        # self._validation_keybindings(*args, **kwargs)
        self.controller = Controller(handle=handle, ign=ign)

    def __call__(self):
        # Idea is maybe we can pass class instances to the Sessionmanager and calling a class is picklable? to test!
        asyncio.run(self.controller.move('left', 5, True))

    # @abstractmethod
    def required_keybindings(self):
        pass

    def _validation_keybindings(self, user_defined_keybindings) -> None:
        assert all(key in self.required_keybindings() for key in user_defined_keybindings), f"Missing keybindings.\nRequired:\n{self.required_keybindings()}\nProvided:\n{user_defined_keybindings}."
