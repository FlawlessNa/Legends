import asyncio
import logging
import multiprocessing

from .bot import Bot

logger = logging.getLogger(__name__)


class BotLauncher:
    """
    Launcher class for all Bots.
    A single, shared asynchronous queue (class attribute) is used to schedule all Bots. This ensures that no two Bots are running in parallel, which would be suspicious.
    Instead of true parallelism, this fully leverages cooperative multitasking.
    Additionally, it defines synchronization primitives that can be used by all bots as well.
    """

    shared_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
    blocker: asyncio.Event = asyncio.Event()

    def __init__(self, logging_queue: multiprocessing.Queue) -> None:
        self.logging_queue = logging_queue
        Bot.logging_queue = logging_queue

    def __enter__(self) -> None:
        for bot in Bot.all_bots:
            bot.set_monitoring_process()
            bot.monitoring_process.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        for bot in Bot.all_bots:
            bot.bot_side.send(None)
            bot.bot_side.close()
            logger.debug(f"Sent stop signal to {bot} monitoring process")
            bot.monitoring_process.join()
            logger.debug(f"Joined {bot} monitoring process")
            logger.debug(f"Stopping {bot} main task")
            bot.main_task.cancel()

    @classmethod
    async def run_all(cls):
        cls.blocker.set()  # Unblocks all Bots

        for bot in Bot.all_bots:
            bot.main_task = asyncio.create_task(
                bot.action_listener(cls.shared_queue), name=repr(bot)
            )
            logger.info(f"Created task {bot.main_task}.")

        while True:
            await cls.blocker.wait()  # Blocks all Bots until a task clears the blocker. Used for Stopping/Pausing all bots through user-request from discord.
            queue_item = await cls.shared_queue.get()
            if queue_item is None:
                break

            for task in asyncio.all_tasks():
                if getattr(task, "priority", 0) > queue_item.priority:
                    logger.debug(
                        f"{queue_item.identifier} has priority over task {task.get_name()}. Cancelling task."
                    )
                    task.cancel()

            # Adds the task into the main event loop
            new_task = asyncio.create_task(
                queue_item.action(), name=queue_item.identifier
            )
            new_task.priority = queue_item.priority

            # Ensures the queue is cleared after the task is done. Callback executes even when task is cancelled.
            new_task.add_done_callback(lambda _: cls.shared_queue.task_done())

            if queue_item.callback is not None:
                new_task.add_done_callback(queue_item.callback)

            logger.debug(f"Created task {new_task}.")

            if len(asyncio.all_tasks()) > 15:
                logger.warning(
                    f"Number of tasks in the event loop is {len(asyncio.all_tasks())}."
                )

    @classmethod
    def cancel_all(cls):
        cls.shared_queue.put_nowait(None)
