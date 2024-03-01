

class EngineListener:
    """
    Lives in the MainProcess.
    An EngineListener is linked to a single Engine instance through a multiprocessing
    Connection. It receives ActionData containers from the Engine and schedules them
    into tasks. It also sends back residual MonitorData attributes to the Engine.
    """