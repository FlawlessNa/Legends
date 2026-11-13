import logging.handlers
import multiprocessing
import os
import threading

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


def exit_with_parent() -> None:
    """
    End this process when its parent does, however the parent ends.

    A child process outlives a parent that is killed from outside (a terminal
    closed, the task manager): nothing tells it, and it would idle on. A thread
    waits for the parent's exit and then ends the process at once. That is safe
    for an Engine and the Peripherals process: neither sends input, so no key is
    left held by their going (Main Process releases keys on the way out, and the
    Held-Keys Ledger belongs to it). A no-op in the main process.
    """
    parent = multiprocessing.parent_process()
    if parent is None:
        return

    def _watch() -> None:
        parent.join()
        os._exit(1)

    threading.Thread(target=_watch, name="Parent Watch", daemon=True).start()
