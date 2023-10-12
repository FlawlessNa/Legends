import logging
import logging.handlers
import multiprocessing
import multiprocessing.connection


class ChildProcess:
    def __init__(self,
                 pipe_end: multiprocessing.connection.Connection,
                 mp_queue: multiprocessing.Queue,
                 logger: logging.Logger) -> None:
        self.pipe_end = pipe_end
        self.log_queue = mp_queue
        logger.addHandler(logging.handlers.QueueHandler(self.log_queue))
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        for handler in logger.parent.handlers:
            handler.close()
            logger.parent.removeHandler(handler)