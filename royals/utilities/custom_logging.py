"""Re defines RotatingFileHandler and StreamHandler to acquire a lock before emitting a log message."""
import logging.handlers
import multiprocessing

import os
class MultiProcessRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._emit_lock = multiprocessing.Lock()
        self._rollover_lock = multiprocessing.Lock()

    # def emit(self, record):
    #     with self._emit_lock:
    #         super().emit(record)
    #
    # def doRollover(self):
    #     print("doRollover")
    #     with self._rollover_lock:
    #         print("lock acquired for doRollover")
    #         super().doRollover()
    #         print("doRollover Completed")


class MultiProcessStreamHandler(logging.StreamHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = multiprocessing.Lock()

    def emit(self, record):
        with self._lock:
            super().emit(record)
