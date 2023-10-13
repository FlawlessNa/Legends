import logging
import logging.handlers
import multiprocessing.connection


class ChildProcess:
    """
    Base class for any child process (spawned through multiprocessing.Process).
    Ensures that the child process has a connection to the main process through a pipe.
    Additionally, any log entries created by a child process is sent to a logging.handlers.QueueHandler.
    The Main Process has a QueueListener that listens to this queue and handles the log entries.
    This allows for all logs to be centralized into the same file.
    """

    def __init__(
        self,
        pipe_end: multiprocessing.connection.Connection,
        mp_queue: multiprocessing.Queue,
        master_logger_name: str = "royals",
    ) -> None:
        """
        For any child process, the "global" logger/handlers are re-created, which is undesired.
        Therefore, we remove all handlers from the parent logger and add a QueueHandler instead.
        That way, any loggers created in child process will only have the QueueHandler.
        :param pipe_end: End of the pipe received by child, used to communicate with parent.
        :param mp_queue: multiprocessing.Queue solely used to send log records to parent.
        """
        self.pipe_end = pipe_end
        self.log_queue = mp_queue

        file_handler = logging.handlers.QueueHandler(self.log_queue)
        file_handler.setLevel(logging.DEBUG)

        master = logging.getLogger(master_logger_name)
        while master.hasHandlers():
            master.handlers[0].close()
            master.removeHandler(master.handlers[0])
        master.addHandler(file_handler)
