

class MonitorData:
    """
    A data container instance used by a Monitor instance to establish communication
    between its DecisionMakers.
    Each Monitor instance has its own MonitorData instance, which is shared with all
    DecisionMakers assigned to it. This is done to allow DecisionMakers to be made aware
    of the overall state of the Monitor, since each DecisionMaker may alter that state.
    """
    pass
