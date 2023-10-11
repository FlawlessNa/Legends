import asyncio
import multiprocessing
import multiprocessing.connection

from functools import partial
from typing import Self

from .bot import Bot
from screen_recorder import Recorder


class SessionManager:
    """
    Entry point to launch any Bot.
    The Manager will handle the following:
        - Establish and kill Discord communications
        - Launch an independent multiprocessing.Process to handle the screen recording. Recording is CPU-intensive and should not be done in the same process as the Bot.
        - Keep track of Logs and save those # TODO
        - Schedule each Bot as tasks to be executed in a single asyncio loop. This ensures no actions are executed in parallel, which would be suspicious.
        - Perform automatic clean-up as necessary. When the Bot is stopped, the Manager will ensure the screen recording is stopped and saved.
    """
    def __init__(self, *bots_to_launch: Bot) -> None:
        self.bots = bots_to_launch
        self.recorder_process = None
        self.receiver, self.sender = multiprocessing.Pipe(duplex=False)

    def __enter__(self) -> Self:
        """
        Setup all Bot tasks.
        Setup Recorder process.
        # TODO - Handle logger?
        :return: self
        """
        self.recorder_process = multiprocessing.Process(target=self.create_recorder, name='Screen Recorder', args=(self.receiver, ))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Whenever the context manager is exited, that means the asynchronous loop's execution has halted, for whatever reason. In such a case, all Bots are already stopped.
        Assuming the Bots handle their own clean-up, the only thing left to do is to stop the screen recording and save it. To do send, we send a signal to the isolated recording Process.
        :param exc_type: Exception Class.
        :param exc_val: Exception Value (instance).
        :param exc_tb: Exception Traceback.
        :return: None
        """
        self.sender.send('stop')
        self.recorder_process.join()

    @staticmethod
    def create_recorder(receiver: multiprocessing.connection.Connection):
        def f(recv_end: multiprocessing.connection.Connection):
            if recv_end.poll():  # Check if a signal has been sent from the other end of the Pipe
                signal = recv_end.recv()
                if signal == 'stop':
                    return True
            return False

        recorder = Recorder(partial(f, receiver))
        recorder.start_recording()

    async def launch(self) -> None:
        self.recorder_process.start()
        async with asyncio.TaskGroup() as tg:
            for bot in self.bots:
                tg.create_task(bot.run())
