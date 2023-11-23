import logging
import multiprocessing.connection

from unittest import TestCase
from unittest.mock import MagicMock

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

    @classmethod
    def setUpClass(cls) -> None:
        """
        Idea is to create multiple child processes and have them all log to the same queue.
        We check that each logger within the child processes has a single handler (the QueueHandler).
        We further check that this QueueHandler pushes each log record towards the same multiprocessing.Queue object.
        Lastly, we check that the main process has a QueueListener that listens to this queue and handles the log records.
        :return:
        """
        def _child_proc(queue: multiprocessing.Queue) -> None:
            ChildProcess.set_log_queue(queue)
            child_logger = logging.getLogger('botting')

            assert len(child_logger.handlers) == 1
            assert isinstance(child_logger.handlers[0], logging.handlers.QueueHandler)
            assert child_logger.handlers[0].queue is queue

        cls.logger = logging.getLogger('botting')
        cls.queue = multiprocessing.Queue()
        cls.children = [multiprocessing.Process(target=_child_proc, name=f'{i}', args=(cls.queue,)) for i in range(5)]

    @classmethod
    def tearDownClass(cls) -> None:
        pass

    def test___init__(self):
        fake_pipe = MagicMock(multiprocessing.connection.Connection)
        with self.assertRaises(AssertionError):
            ChildProcess(fake_pipe)

    def test_set_log_queue(self):
        self.assertEqual(ChildProcess.log_queue, None)
        ChildProcess.set_log_queue(self.queue)
        self.assertIs(ChildProcess.log_queue, self.queue)
