from dataclasses import field, dataclass
from typing import Coroutine


@dataclass
class ActionRequest:
    """
    A data container sent by any DecisionMaker to the Main process.
    May contain the following:
    - Action to be performed, if any
    - BotData attributes to be updated after the action is performed, if any
    - Request to block/unblock any other DecisionMaker(s) from any Bot/Engine.
    - Any Message to be sent to the user through the Peripheral Process.
    - Any task priority and scheduling attribute, used by Main Process to handle
    task management.
    """

    procedure: Coroutine
    identifier: str
    priority: int
    requeue_if_not_scheduled: bool = field(default=True)
    cancellable_by_self: bool = field(default=True)
    cancellable_by_others: bool = field(default=True)
    callback: callable = field(default=None)
