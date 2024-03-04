import logging
import logging.handlers
import multiprocessing

import botting

logger = logging.getLogger(__name__)


def setup_child_proc_logging(log_queue: multiprocessing.Queue) -> None:
    """
    Sets up the logging for the child process.
    :param log_queue: The multiprocessing.Queue instance to which the log entries
     will be sent by a logging.handlers.QueueHandler.
    :return: None
    """
    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setLevel(logging.DEBUG)

    root = logging.getLogger(botting.PARENT_LOG)
    while root.hasHandlers():
        root.handlers[0].close()
        root.removeHandler(root.handlers[0])
    root.addHandler(queue_handler)
