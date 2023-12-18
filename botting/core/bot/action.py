from dataclasses import field, dataclass
from typing import Optional


@dataclass(order=True)
class QueueAction:
    """
    A dataclass that represents an action to be executed in the queue. It is used to store the priority, identifier and actual task for the action to be executed.
    Only the priority is used to compare which actions to be executed next.
    """

    identifier: str = field(compare=False)
    priority: int = field()
    action: callable = field(compare=False, repr=False)
    is_cancellable: bool = field(compare=False, default=False, repr=False)
    is_map_rotation: bool = field(compare=False, default=False, repr=False)
    lock_id: int = field(compare=False, default=None, repr=False)
    update_game_data: Optional[tuple[str] | dict] = field(
        compare=False, default=None, repr=False
    )
    callbacks: list[callable] = field(compare=False, default_factory=list, repr=False)
