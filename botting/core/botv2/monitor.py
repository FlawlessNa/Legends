from abc import ABC, abstractmethod

from .monitor_data import MonitorData
from .decision_maker import DecisionMaker


class Monitor:
    """
    Abstract base class to represent a Monitor of any kind.
    A Monitor is a container of DecisionMakers, which are cycled and called
    one at a time.

    A monitor represents a single game client entity and is assigned a single
    MonitorData instance which it shares with all its DecisionMakers.
    """
