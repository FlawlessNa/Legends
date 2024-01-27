from dataclasses import field, dataclass
from functools import partial
from typing import Optional

from botting.utilities import get_object_by_id


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
    action: partial = field(compare=True, repr=False, default=None)
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
    generator_args: tuple = field(default_factory=tuple)
    generator_kwargs: dict = field(default_factory=dict)

    def update_when_done(self, data) -> None:
        """
        Updates the game data and the generator when the queue action is completed.
        if Generator_id = 0, this is a special case from a discord user-request that affects all generators.
        """
        data.update(*self.game_data_args, **self.game_data_kwargs)

        if self.generator_id is not None:
            generator = get_object_by_id(self.generator_id)

            # TODO - Test if this works?
            for arg in self.generator_args:
                assert hasattr(generator, arg), f"Invalid attribute {arg}"
                assert callable(getattr(generator, arg)), f"Invalid attribute {arg}"
                func = getattr(generator, arg)
                func()

            for k, v in self.generator_kwargs.items():
                assert hasattr(generator, k), f"Invalid attribute {k}"
                setattr(generator, k, v)


@dataclass
class CompoundAction(QueueAction):
    """
    A complex QueueAction that could usually be broken down into several QueueActions.
    The difference is that CompoundAction may require CPU-intensive operations that
    will be performed WITHIN the main process.
    When a Generator submits a CompoundAction to the main process, the engine containing
    that generator is expected to be blocked while the entire CompoundAction executes.
    The CompoundAction must therefore send a GeneratorUpdate signal to the appropriate
    engine when it is done.

    Since CompoundAction live in the main process, they must manually define everything
    they need to properly perform the operations (UI-related objects, for example).
    """
    pass
