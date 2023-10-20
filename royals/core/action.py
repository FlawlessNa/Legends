from dataclasses import field, dataclass
from typing import Optional


@dataclass(order=True)
class QueueAction:
    """
    A dataclass that represents an action to be executed in the queue. It is used to store the priority, identifier and actual task for the action to be executed.
    Only the priority is used to compare which actions to be executed next.
    """

    priority: int = field()
    identifier: str = field(compare=False)
    action: callable = field(compare=False)
    callback: Optional[callable] = field(compare=False, default=None)

    @property
    def item(self) -> tuple[int, str, callable, Optional[callable]]:
        return self.priority, self.identifier, self.action, self.callback

    @classmethod
    def from_tuple(cls, value: tuple[int, str, callable, Optional[callable]]):
        assert len(value) == 3
        assert isinstance(value[0], int)
        assert isinstance(value[1], str)
        assert callable(value[2])
        assert value[3] is None or callable(value[3])
        return cls(*value)
