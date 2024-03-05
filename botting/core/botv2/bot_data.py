

class BotData:
    """
    A data container instance used by a Monitor instance to establish communication
    between its DecisionMakers.
    Each Bot instance has its own BotData instance, which is shared with all
    DecisionMakers assigned to it. This is done to allow DecisionMakers to be made aware
    of the overall state of the Bot, since each DecisionMaker may alter that state.
    """
    pass
