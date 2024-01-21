import ctypes
from dataclasses import field, dataclass
from functools import partial
from typing import Optional

from .game_data import GameData


@dataclass
class QueueAction:
    """
    A dataclass that represents an action to be executed in the queue.
    Usually created within a DecisionGenerator(Child process) and sent to Main process.
    It is used to store the priority, identifier and actual task (action) to execute.

    An action with a higher priority will cancel all running actions that are
    cancellable and have a lower priority.

    If update_game_data is provided, then once the action is completed or cancelled,
    the data to update is sent back into the appropriate DecisionEngine (through IPC).

    If user_message is provided, then a discord message is sent to the user once the
    action terminates.

    If release_lock_on_callback is True, a multiprocessing.Lock will be released once
    the action terminates.

    callbacks: Not yet implemented. This will be used to perform a callback within
    the Main Process (NOT the DecisionEngine) once the action completes or cancels.
    """

    identifier: str = field(compare=False)
    priority: int = field()
    action: partial = field(compare=True, repr=False)
    is_cancellable: bool = field(compare=False, default=False, repr=False)
    user_message: list = field(compare=False, default=None, repr=False)

    update_generators: Optional["GeneratorUpdate"] = field(
        compare=False, default=None, repr=False
    )
    release_lock_on_callback: bool = field(compare=False, default=False, repr=False)

    # Not yet implemented
    callbacks: list[callable] = field(compare=False, default_factory=list, repr=False)

    def __eq__(self, other):
        return (
                self.action.func == other.action.func and
                self.action.keywords == other.action.keywords and
                self.action.args == other.action.args
        )


@dataclass
class GeneratorUpdate:
    """
    A dataclass that represents the data to update in a DecisionEngine.
    It is used to send data back to the DecisionEngine (from the Main proc) through IPC.
    QueueActions are sent to Main process to be executed. Upon completion, their
    GeneratorUpdate attribute (if provided) is sent back to the appropriate
    DecisionEngine.
    """
    game_data_args: tuple = field(default_factory=tuple)
    game_data_kwargs: dict = field(default_factory=dict)

    generator_id: int = field(default=None)
    generator_args: tuple = NotImplemented
    generator_kwargs: dict = field(default_factory=dict)

    def update_generator(self) -> None:
        """
        Updates the game data and the generator.
        """
        if self.generator_id is not None:
            generator = self.get_object_by_id(self.generator_id)
            if not isinstance(self.generator_args, type(NotImplemented)):
                raise NotImplementedError("Generator args not implemented")

            for k, v in self.generator_kwargs.items():
                assert hasattr(generator, k), f"Invalid attribute {k}"
                setattr(generator, k, v)

    def update_game_data(self, data: GameData) -> None:
        data.update(*self.game_data_args, **self.game_data_kwargs)

    @staticmethod
    def get_object_by_id(obj_id: int) -> object:
        """
        Retrieves an object based on its ID.
        """
        return ctypes.cast(obj_id, ctypes.py_object).value
