import logging.handlers
import multiprocessing.connection

from unittest import TestCase
from unittest.mock import MagicMock

from botting import PARENT_LOG
from botting.utilities import ChildProcess

# TODO - Use subprocess as below to check if a file is open by how many process (the log file).
# import subprocess
#
# def get_open_processes(file_path):
#     try:
#         output = subprocess.check_output(['lsof', file_path])
#         lines = output.decode().split('\n')
#         # Skip the first line (header) and the last line (empty)
#         processes = [line.split()[1] for line in lines[1:-1]]
#         return processes
#     except subprocess.CalledProcessError:
#         # Handle the case when the file is not opened by any process
#         return []
#
# # Example usage
# file_path = '/path/to/log/file.log'
# open_processes = get_open_processes(file_path)
# print(f"The file is opened by {len(open_processes)} processes: {open_processes}")


class TestChildProcess(TestCase):
    """
    The ChildProcess class has a few purposes. The idea here is to test that these purposes are fulfilled.
    1. Ensure that the logger object used within each child process has a single handler, which is a logging.handlers.QueueHandler.
    2. Ensure that the QueueHandler used within each child process pushes log records to the same multiprocessing.Queue object.
    3. Ensure that the main process has a QueueListener that listens to this queue and handles the log records.
    4. Lastly and analogous to the first item, ensure that the log file used by the main process is not opened by any child process.
    """

    shared_queue = multiprocessing.Queue()
    fake_pipe = MagicMock(multiprocessing.connection.Connection)
    nbr_subprocesses = 5

    @classmethod
    def setUpClass(cls) -> None:
        pass

    @classmethod
    def tearDownClass(cls) -> None:
        pass

    @staticmethod
    def _child_proc(queue: multiprocessing.Queue, pipe: multiprocessing.connection.Connection) -> None:
        """Creates a child process that logs a test message."""
        ChildProcess.set_log_queue(queue)
        child_proc = ChildProcess(pipe)
        child_logger = logging.getLogger('botting')

        # From the child process, log how many handlers there are (expected 1), and whether the handler is a QueueHandler.
        child_logger.info(len(child_logger.handlers) == 1)
        child_logger.info(isinstance(child_logger.handlers[0], logging.handlers.QueueHandler))

    def test_all_items(self):
        # Create a few child processes that each two messages.
        processes = [multiprocessing.Process(target=self._child_proc, args=(self.shared_queue, None), name=f'{i}') for i in range(self.nbr_subprocesses)]
        for process in processes:
            process.start()
        for process in processes:
            process.join()

        all_logs = []
        while not self.shared_queue.empty():
            all_logs.append(self.shared_queue.get())

        # Confirm that the first item outlined above is fulfilled.
        self.assertTrue(all(eval(log_record.msg) for log_record in all_logs))

        # Confirm that the second item outlined above is fulfilled.
        excepted_messages = self.nbr_subprocesses * 2
        self.assertEqual(len(all_logs), excepted_messages)

        # Confirm that the third item outlined above is fulfilled.
        self.assertEqual(len(all_logs), excepted_messages)



    def test_set_log_queue(self):

        self.assertEqual(ChildProcess.log_queue, None)
        with self.assertRaises(AssertionError):
            # Cannot create a ChildProcess instance before setting the log queue.
            ChildProcess(self.fake_pipe)

        ChildProcess.set_log_queue(self.shared_queue)
        self.assertIs(ChildProcess.log_queue, self.shared_queue)
        self.assertIsInstance(ChildProcess(self.fake_pipe), ChildProcess)  # Can create a ChildProcess instance after setting the log queue.
