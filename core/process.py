from abc import ABC, abstractmethod


class Process(ABC):
    def __init__(self, *args, **kwargs) -> None:
        self._validation_keybindings(*args, **kwargs)

    @abstractmethod
    def required_keybindings(self):
        pass

    def _validation_keybindings(self, user_defined_keybindings) -> None:
        assert all(key in self.required_keybindings() for key in user_defined_keybindings), f"Missing keybindings.\nRequired:\n{self.required_keybindings()}\nProvided:\n{user_defined_keybindings}."
