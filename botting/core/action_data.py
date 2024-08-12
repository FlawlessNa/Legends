import asyncio
from dataclasses import field, dataclass


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

    procedure: callable
    identifier: str
    ign: str
    priority: int = field(default=1)  # Higher priority tasks have more control

    # Whether to cancel a task with same identifier
    cancels_itself: bool = field(default=False)

    # Used when this task is blocked from being scheduled by another task
    requeue_if_not_scheduled: bool = field(default=True)

    # Used to block lower priority tasks from being scheduled
    block_lower_priority: bool = field(default=False)

    callback: callable = field(default=None)
    task: asyncio.Task = field(default=None, init=False)
    discord_request: "DiscordRequest" = field(default=None)


@dataclass
class DiscordRequest:
    pass  # TODO: Implement this
