import logging
import logging.handlers
import multiprocessing.connection

import botting


class ChildProcess:
    """
    Base class for any child process (spawned through multiprocessing.Process).
    Ensures that the child process has a connection to the main process through a pipe.
    Additionally, any log entries created by a child process is sent to a logging.handlers.QueueHandler.
    The Main Process has a QueueListener that listens to this queue and handles the log entries.
    This allows for all logs to be centralized into the same file.
    """

    log_queue: multiprocessing.Queue = None

    def __init__(
        self,
        pipe_end: multiprocessing.connection.Connection,
    ) -> None:
        """
        For any child process, the "global" logger/handlers are re-created, which is undesired.
        Therefore, we remove all handlers from the parent logger and add a QueueHandler instead.
        That way, any loggers created in child process will only have the QueueHandler.
        The LogQueue class attribute must be set (within the child process) before any instance of ChildProcess is created.
        :param pipe_end: End of the pipe received by child, used to communicate with parent.
        """
        assert (
            self.log_queue is not None
        ), "Log Queue must be set before creating any child process."
        self.pipe_end = pipe_end
        file_handler = logging.handlers.QueueHandler(self.log_queue)
        file_handler.setLevel(logging.DEBUG)

        root = logging.getLogger(botting.PARENT_LOG)
        while root.hasHandlers():
            root.handlers[0].close()
            root.removeHandler(root.handlers[0])
        root.addHandler(file_handler)

    @classmethod
    def set_log_queue(cls, queue: multiprocessing.Queue) -> None:
        """
        Method to call from within a child process before creating a ChildProcess instance
        (or any class instance that inherits from ChildProcess).
        :param queue: The queue to which the log entries will be sent. The main process will dispatch the log entries to the appropriate handlers.
        """
        cls.log_queue = queue
