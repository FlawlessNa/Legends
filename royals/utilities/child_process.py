import multiprocessing.connection


class ChildProcess:
    def __init__(self, pipe_end: multiprocessing.connection.Connection) -> None:
        self.pipe_end = pipe_end
