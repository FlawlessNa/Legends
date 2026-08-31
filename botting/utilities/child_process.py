import logging.handlers
import multiprocessing

from botting import PARENT_LOG


def setup_child_proc_logging(log_queue: multiprocessing.Queue) -> None:
    """
    Point this process' logging at the queue Main Process drains.

    Every record this process emits travels QueueHandler -> queue ->
    ``QueueListener`` -> the handlers `SessionManager` built. The child owns no
    file of its own, so any handler already attached here is dropped first.

    :param log_queue: The queue a ``logging.handlers.QueueListener`` drains in
     Main Process.
    :return: None
    """
    parent = logging.getLogger(PARENT_LOG)

    # Iterate over a copy of this logger's *own* handler list. `hasHandlers()`
    # walks up the hierarchy, so the loop this replaces terminated only because
    # `levels_config()` happens to set `propagate: False` one module over - and
    # had `botting` ever been handler-less while the root logger was not, it
    # would have raised IndexError indexing a list that never shrinks.
    for handler in parent.handlers[:]:
        # Removed before closed, so a record logged from another thread can
        # never reach a handler whose stream is already shut.
        parent.removeHandler(handler)
        handler.close()

    queue_handler = logging.handlers.QueueHandler(log_queue)
    queue_handler.setLevel(logging.DEBUG)
    parent.addHandler(queue_handler)
