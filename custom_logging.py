import logging
import multiprocessing


class MultiProcessFileHandler(logging.FileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = multiprocessing.Lock()

    def emit(self, record):
        with self._lock:
            super().emit(record)


class MultiProcessStreamHandler(logging.StreamHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = multiprocessing.Lock()

    def emit(self, record):
        with self._lock:
            super().emit(record)
