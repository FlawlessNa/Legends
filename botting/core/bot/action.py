from dataclasses import field, dataclass
from functools import partial
from typing import Optional, Generator


@dataclass
class QueueAction:
    """
    A dataclass that represents an action to be executed in the queue. It is used to store the priority, identifier and actual task for the action to be executed.
    Only the priority is used to compare which actions to be executed next.
    """

    identifier: str = field(compare=False)
    priority: int = field()
    action: partial = field(compare=True, repr=False)
    is_cancellable: bool = field(compare=False, default=False, repr=False)
    update_game_data: Optional[tuple | dict] = field(
        compare=False, default=None, repr=False
    )
    user_message: list = field(compare=False, default=None, repr=False)
    release_lock_on_callback: bool = field(compare=False, default=False, repr=False)
    callbacks: list[callable] = field(compare=False, default_factory=list, repr=False)

    def __eq__(self, other):
        return self.action.func == other.action.func and self.action.keywords == other.action.keywords and self.action.args == other.action.args

    @classmethod
    def action_generator(
        cls,
        *,
        release_lock_on_callback: bool = False,
        cancellable: bool = False,
        priority: int = 99,
        callbacks: list[callable] = None
    ) -> callable:
        """
        A decorator that is used to wrap a generator function that yields actions to be executed in the queue.
        Retrieve the output from the generator and wrap it in a QueueAction.
        :return: A QueueAction.
        """

        def _decorator(generator: callable) -> callable:
            def _wrapper(*args, **kwargs) -> Generator:
                generator_instance = generator(*args, **kwargs)
                while True:
                    action = next(generator_instance)
                    if action:
                        yield cls(
                            identifier=" ".join(
                                [i.capitalize() for i in generator.__name__.split("_")]
                            ),
                            priority=priority,
                            action=action,
                            is_cancellable=cancellable,
                            update_game_data=kwargs.get("update_game_data", None),
                            release_lock_on_callback=release_lock_on_callback,
                            callbacks=callbacks if callbacks is not None else [],
                        )
                    else:
                        yield

            return _wrapper

        return _decorator
