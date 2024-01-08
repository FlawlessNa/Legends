import asyncio
import cv2
import discord
import logging
import multiprocessing.connection
import numpy as np
import os

from functools import cached_property

from botting.utilities import ChildProcess, config_reader

logger = logging.getLogger(__name__)


class DiscordLauncher:
    """
    Launches a DiscordComm ChildProcess, responsible for communication with Discord.
    While discord API is already asynchronous, we want to ensure that the bots are
     not blocked by any Discord-related actions.
    Therefore, we launch a separate Process to handle Discord communications.
    """

    def __init__(self, queue: multiprocessing.Queue) -> None:
        # Two-way communication
        self.main_side, self.discord_side = multiprocessing.Pipe()
        self.logging_queue = queue
        self.discord_process = None

    def __enter__(self) -> None:
        self.discord_process = multiprocessing.Process(
            target=self.start_discord_comms,
            name="Discord Communication",
            args=(self.discord_side, self.logging_queue),
        )
        self.discord_process.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.main_side.send(None)
        self.main_side.close()
        logger.debug("Sent stop signal to discord process")

        self.discord_process.join()
        logger.info(f"DiscordLauncher exited.")

    @staticmethod
    def start_discord_comms(
        pipe_end: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue,
    ):
        discord_comm = DiscordComm(log_queue, pipe_end)
        asyncio.run(discord_comm.start())


class DiscordComm(discord.Client, ChildProcess):
    """
    Establishes communication with Discord,
     while maintaining the end of a Pipe object to communicate with the main process.
    """

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        pipe_end: multiprocessing.connection.Connection,
    ) -> None:
        super().__init__(intents=discord.Intents.all())
        self.config = config_reader("discord")
        self.config_section = f"User {self.config['DEFAULT']['user']}"
        ChildProcess.__init__(self, log_queue, pipe_end)

    @cached_property
    def chat_id(self) -> int:
        """
        Retrieves the Specified chat channel,
         which is the channel used for all communications within the current session.
        :return:
        """
        return [
            i.id
            for i in self.get_all_channels()
            if i.name == self.config[self.config_section]["DISCORD_CHANNEL"]
            and i.type.name == "text"
        ].pop()

    async def on_ready(self) -> None:
        """
        Callback function triggered by discord.Client when connection is established.
        """
        logger.info(f"Discord Communication Established with {self.user}.")

    async def on_message(self, msg: discord.Message) -> None:
        """
        Callback that is triggered every time a message is sent/received
         from the discord channel.
        The message source is first checked. If it is from the bot itself,
         then it is ignored. If it is from current user, then message is passed
         on to main process for parsing.
        :param msg: The message instance.
        :return:
        """

        # No need to process messages sent by bot. If the author is the bot, return
        if msg.author == self.user:
            return

        # Ensures only messages from specified discord user are processed.
        # Additionally, messages must be sent in the specified channel.
        elif (
            msg.author.id != int(self.config[self.config_section]["DISCORD_ID"])
            or msg.channel.name != self.config[self.config_section]["DISCORD_CHANNEL"]
        ):
            return

        logger.info(
            f"Received message from {msg.author.name}#{msg.author.discriminator} in channel {msg.channel.name}. Contents: {msg.content}"
        )
        self.pipe_end.send(msg.content)  # Send message to main process for parsing

    async def start(self, *args, **kwargs) -> None:
        """
        Creates a TaskGroup to run the Discord client asynchronously
         with the listener.
        The discord client listens for discord events. and relays to main.
        The listener listens for signals from the main process and relays to discord.
        """
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                discord.Client.start(self, self.config["DEFAULT"]["DISCORD_TOKEN"])
            )
            tg.create_task(self.relay_main_to_disc())

    async def relay_main_to_disc(self) -> None:
        """
        Child Process task.
        This method is responsible for listening to the main process.
        If main process sends a None signal, then it means the process is shutting down
         and this method will close both the Discord client and the listener.
        Otherwise, the signal is assumed to be a message meant for the user.
        It is sent to the specified chat channel on Discord.
        :return: None
        """
        while True:
            # Check if a signal is received from main process, blocks Discord Process
            # for 2 seconds, meaning Discord.client is idle during this time.
            if await asyncio.to_thread(self.pipe_end.poll):
                signal = self.pipe_end.recv()
                if signal is None:
                    logger.info("Stopping Discord Communications.")
                    self.pipe_end.close()
                    await self.close()
                    break
                else:
                    if isinstance(signal, str):
                        logger.info(
                            f"{self.__class__.__name__} received a signal {signal}. Sending to Discord."
                        )
                        await self.get_channel(self.chat_id).send(signal)
                    elif isinstance(signal, np.ndarray):
                        cv2.imwrite('temp.png', signal)
                        with open("temp.png", "rb") as f:
                            await self.get_channel(self.chat_id).send(file=discord.File(f))
                        # Now delete the file
                        os.remove("temp.png")

                    else:
                        raise NotImplementedError
