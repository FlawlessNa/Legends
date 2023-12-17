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

    def __new__(
        cls,
        log_queue: multiprocessing.Queue,
        pipe_end: multiprocessing.connection.Connection,
    ) -> "ChildProcess":
        """
        Before creating a new instance, make sure that the class attribute log_queue is not set.
        This ensures that there is only a single instance of ChildProcess per Python Process.
        Then, set the log_queue and create a new instance of the class.
        :param log_queue: The multiprocessing.Queue instance to which the log entries will be sent by a logging.handlers.QueueHandler.
        :param pipe_end: The end of the pipe that is connected to the main process, used to communicate anything other than log records.
        :return: The instance of the class.
        """
        instance = object.__new__(cls)
        if cls.log_queue is None:
            cls.log_queue = log_queue
        else:
            raise RuntimeError(
                "There should only be a single ChildProcess instance per Python Process."
            )
        return instance

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        pipe_end: multiprocessing.connection.Connection,
    ) -> None:
        """
        For each child process, we want to ensure that the log entries are sent to the same queue by a QueueHandler.
        Therefore, we remove all other handlers from the parent logger and add a QueueHandler instead.
        That way, any loggers created in child process will only have the QueueHandler and no other handler.
        :param log_queue: The multiprocessing.Queue instance to which the log entries will be sent by a logging.handlers.QueueHandler.
        :param pipe_end: End of the pipe received by child, used to communicate with parent.
        """
        assert (
            self.log_queue is log_queue
        ), "Log Queue must be set before creating any child process."
        self.pipe_end = pipe_end
        queue_handler = logging.handlers.QueueHandler(log_queue)
        queue_handler.setLevel(logging.DEBUG)

        root = logging.getLogger(botting.PARENT_LOG)
        while root.hasHandlers():
            root.handlers[0].close()
            root.removeHandler(root.handlers[0])
        root.addHandler(queue_handler)
