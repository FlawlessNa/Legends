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
    is_cancellable: bool = field(compare=False, default=False)
    is_map_rotation: bool = field(compare=False, default=False)
    release_rotation_lock: bool = field(compare=False, default=False)
    update_game_data: Optional[tuple[str]] = field(compare=False, default=None)
    callbacks: list[callable] = field(compare=False, default_factory=list)
