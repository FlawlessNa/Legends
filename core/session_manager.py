import asyncio
import multiprocessing
import multiprocessing.connection

from functools import partial
from typing import Coroutine, Self

from screen_recorder import Recorder


class SessionManager:
    """
    Entry point to launch any Bot session, which may consists of one or more processes.
    The Manager will handle the following:
        - Establish and kill Discord communications
        - Start screen recording and save session (through multiprocessing, since this is not related to the game and is CPU-intensive)
        - Keep track of Logs and save those
        - Start and stop the Bot (process(es)) (through asyncio, since this is related to the game and asyncio runs on a single-process/single-thread, which is more human-like).
    """
    # def __init__(self, *coroutines: Coroutine) -> None:
    #     self.coroutines: tuple[Coroutine] = coroutines
    def __init__(self, f: callable) -> None:
        self.f: callable = f
        self.bot_process = None
        self.recorder_process = None
        self.receiver, self.sender = multiprocessing.Pipe(duplex=False)

    def __enter__(self) -> Self:
        """
        Setup all tasks and processes.
        :return: self
        """
        self.bot_process = multiprocessing.Process(target=self.f, name='Multi-Bot')

        recorder_check = partial(self.check_recv_signal, self.receiver)
        self.recorder_process = multiprocessing.Process(target=self.create_recorder, name='Screen Recorder', args=(recorder_check, ))

        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.bot_process.join()
        self.sender.send('stop')
        self.recorder_process.join()

        # self._release_all_keys()
        # self.recorder.stop_and_save()
    #
    # async def _asynchronous_process(self):
    #     async with asyncio.TaskGroup() as tg:
    #         for coroutine in self.coroutines:
    #             tg.create_task(coroutine)
    #
    # def _release_all_keys(self):
    #     print('Releasing all keys')
    #     pass

    @staticmethod
    def create_recorder(func: callable):
        recorder = Recorder(func)
        recorder.start()

    @staticmethod
    def check_recv_signal(recv_end: multiprocessing.connection.Connection) -> bool:
        if recv_end.poll():
            signal = recv_end.recv()
            if signal == 'stop':
                return True
        return False

    def start(self) -> None:
        self.bot_process.start()
        self.recorder_process.start()


# if __name__ == '__main__':
#     handle = 0x001A05F2
#     from core.controller import Controller
#     test = Controller(handle, 'FarmFest1')
#
#     async def _test():
#         await test.move('right', 5, True)
#
#     with SessionManager(_test) as manager:
#         manager.start()
