import asyncio
import discord
import multiprocessing.connection


async def _peripherals_tasks(
        pipe_to_main: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue
):
    disc_sentinel = DiscordSentinel(pipe_to_main, log_queue)
    recorder = Recorder(pipe_to_main, log_queue)
    async with asyncio.TaskGroup() as tg:
        client_task = tg.create_task(
            discord.Client.start(...), name="Discord Listener"
        )
        disc_sentinel_task = tg.create_task(
            disc_sentinel.relay_from_main(), name="Relaying to Discord"
        )
        recorder_task = tg.create_task(recorder.start(), name="Screen Recorder")


def peripherals_tasks(
        pipe_to_main: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue
):
    asyncio.run(_peripherals_tasks(pipe_to_main, log_queue))