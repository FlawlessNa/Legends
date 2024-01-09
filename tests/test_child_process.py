import logging.handlers
import multiprocessing.connection
import os

from unittest import TestCase
from unittest.mock import MagicMock

from botting import PARENT_LOG
from botting.utilities import ChildProcess


class TestChildProcess(TestCase):
    """
    The idea here is to test the ChildProcess class as well as the setup of the logging system, which is coded in the botting.__init__.py file.
    Both the ChildProcess class and the botting.__init__ script have a few purposes. The idea here is to test that these purposes are fulfilled.
    1. Ensure that the logger object used within each child process has a single handler, which is a logging.handlers.QueueHandler.
    2. Ensure that the QueueHandler used within each child process pushes log records to the same multiprocessing.Queue object.
    3. Ensure that the QueueListener from main process successfully receives those log messages.
    4. Ensure that the log file used by the main process is properly rotated when a large number of log records is emitted.
    """

    shared_queue = multiprocessing.Queue()
    fake_pipe = MagicMock(multiprocessing.connection.Connection)
    listener = logging.handlers.QueueListener(
        shared_queue,
        *logging.getLogger(PARENT_LOG).handlers,
        respect_handler_level=True,
    )
    nbr_subprocesses = 5

    @staticmethod
    def _child_proc_one_two(
        queue: multiprocessing.Queue, pipe: multiprocessing.connection.Connection
    ) -> None:
        """
        Creates a child process that logs a test message.
        The test message is a boolean expression that is expected to evaluate to True.
        """
        child_proc = ChildProcess(queue, pipe)
        child_logger = logging.getLogger(PARENT_LOG)

        # From the child process, log how many handlers there are (expected 1), and whether the handler is a QueueHandler.
        child_logger.debug(len(child_logger.handlers) == 1)
        child_logger.debug(
            isinstance(child_logger.handlers[0], logging.handlers.QueueHandler)
        )

    @staticmethod
    def _child_proc_three_four(
        queue: multiprocessing.Queue,
        pipe: multiprocessing.connection.Connection,
        nbr_logs_per_child: int,
    ) -> None:
        """Creates a child process that logs a test message."""
        child_proc = ChildProcess(queue, pipe)
        child_logger = logging.getLogger(PARENT_LOG)

        for i in range(nbr_logs_per_child):
            child_logger.debug(f"Child {multiprocessing.current_process().name} - {i}")

    def test_items_one_and_two(self):
        """
        This test ensures that the first two items outlined above are fulfilled.
        1. Ensure that the logger object used within each child process has a single handler, which is a logging.handlers.QueueHandler.
        2. Ensure that the QueueHandler used within each child process pushes log records to the same multiprocessing.Queue object.
        :return:
        """
        # Create a few child processes that each log two records.
        processes = [
            multiprocessing.Process(
                target=self._child_proc_one_two,
                args=(self.shared_queue, None),
                name=f"{i}",
            )
            for i in range(self.nbr_subprocesses)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join()

        all_logs = []
        while not self.shared_queue.empty():
            # Retrieve the log records.
            all_logs.append(self.shared_queue.get())

        # Confirm that the first item outlined above is fulfilled (all records should evaluate to True).
        self.assertTrue(all(eval(log_record.msg) for log_record in all_logs))

        # Confirm that the second item outlined above is fulfilled (Each child process is expected to have logged two records).
        excepted_messages = self.nbr_subprocesses * 2
        self.assertEqual(len(all_logs), excepted_messages)

    def test_items_three_four(self) -> None:
        """
        This test ensures that the third and fourth items outlined above are fulfilled.
        3. Ensure that the QueueListener from main process successfully receives those log messages.
        4. Ensure that the log file used by the main process is properly rotated when a large number of log records is emitted.
            If 4. is True, then it means a single FileHandler is opened by the main process. Otherwise, the file rotation would return an error.
        :return:
        """
        processes = [
            multiprocessing.Process(
                target=self._child_proc_three_four,
                args=(
                    self.shared_queue,
                    None,
                    int(100000 / self.nbr_subprocesses),
                ),  # Log a very large number of records such that the file is rotated.
                name=f"{i}",
            )
            for i in range(self.nbr_subprocesses)
        ]

        i = 0

        def wrapper(emit_func: callable) -> callable:
            """
            This wrapper is used to count the number of times the emit function is called on a Handler.
            :param emit_func: the emit function of a Handler.
            :return:
            """

            def inner(*args, **kwargs):
                nonlocal i
                i += 1
                return emit_func(*args, **kwargs)

            return inner

        initial_nbr_log_files = 0
        for handler in self.listener.handlers:
            # Wrap the emit function of the RotatingFileHandler to count the number of times it is called.
            if isinstance(handler, logging.handlers.RotatingFileHandler):
                handler.emit = wrapper(handler.emit)
                initial_nbr_log_files = len(
                    os.listdir(os.path.dirname(handler.baseFilename))
                )

        self.listener.start()
        for process in processes:
            process.start()

        for process in processes:
            process.join()
        self.listener.stop()

        # Confirm that the third item outlined above is fulfilled.
        self.assertEqual(i, 100000)

        # Confirm that the fourth item outlined above is fulfilled, by ensuring at least 1 new log file exists.
        log_path = os.path.dirname(self.listener.handlers[0].baseFilename)
        self.assertGreaterEqual(len(os.listdir(log_path)), initial_nbr_log_files + 1)

    def tearDown(self) -> None:
        """
        Clean up the log files.
        """
        log_path = os.path.dirname(self.listener.handlers[0].baseFilename)
        for handler in self.listener.handlers:
            handler.close()
        for file in os.listdir(log_path):
            if file.endswith(".log"):
                os.remove(os.path.join(log_path, file))
