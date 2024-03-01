from dataclasses import field, dataclass


@dataclass
class ActionData:
    """
    A data container sent by any DecisionMaker to the Main process.
    May contain the following:
    - Action to be performed, if any
    - MonitorData attributes to be updated after the action is performed, if any
    - Request to block/unblock any other DecisionMaker(s) from any Monitor/Engine.
    - Any Message to be sent to the user through the Peripheral Process.
    - Any task priority and scheduling attribute, used by Main Process to handle
    task management.
    """
    pass
