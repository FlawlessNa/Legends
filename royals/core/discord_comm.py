import asyncio
import discord
import logging
import multiprocessing.connection

from functools import cached_property

from royals.utilities import ChildProcess, config_reader

logger = logging.getLogger(__name__)


def parse_message(message: str) -> None:
    pass


class DiscordLauncher:
    """
    Launches a DiscordComm ChildProcess, which is responsible for establishing communication with Discord.
    While discord API is already asynchronous, we want to ensure that the bots are not blocked by any Discord-related actions.
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
        logger.debug("Sent stop signal to discord process")
        self.discord_process.join()

    async def relay_discord_messages_to_main(self) -> None:
        """
        This method is responsible for listening to the discord process and see if any messages are received by discord user.
        :return: None
        """
        while True:
            if await asyncio.to_thread(self.main_side.poll):
                message = self.main_side.recv()
                parse_message(message)
                # if message.lower() == "kill":
                #     logger.info("Received KILL signal from Discord. Stopping all bots.")
                #     for task in asyncio.all_tasks():
                #         if task.get_name() in [
                #             bot.__class__.__name__ for bot in self.bots
                #         ]:
                #             task.cancel()
                #     break
                logger.info(f"Received message from Discord: {message}")

    @staticmethod
    def start_discord_comms(
        pipe_end: multiprocessing.connection.Connection,
        log_queue: multiprocessing.Queue,
    ):
        discord_comm = DiscordComm(pipe_end, log_queue)
        asyncio.run(discord_comm.start())


class DiscordComm(discord.Client, ChildProcess):
    """Establishes communication with Discord, while maintaining the end of a Pipe object to communicate with the main process."""

    def __init__(
        self,
        pipe_end: multiprocessing.connection.Connection,
        logging_queue: multiprocessing.Queue,
    ) -> None:
        super().__init__(intents=discord.Intents.all())
        self.config = config_reader("discord")
        ChildProcess.__init__(self, pipe_end, logging_queue)

    @cached_property
    def general_chat_id(self) -> int:
        """
        Retrieves the General chat channel, which is the default channel used.  # TODO - change this to use desired chat channel from configs.
        :return:
        """
        return [
            i.id
            for i in self.get_all_channels()
            if i.name == "general" and i.type.name == "text"
        ].pop()

    async def on_ready(self) -> None:
        """Callback function triggered by discord.Client whenever connection is established."""
        logger.info(f"Discord Communication Established with {self.user}.")

    async def on_message(self, msg: discord.Message) -> None:
        """
        Callback that is triggered every time a message is sent/received from the discord channel.
        The message source is first checked. If it is from the bot itself, then it is ignored. If it is from current user, then message is passed on to main process for parsing.
        :param msg: The message instance.
        :return:
        """

        # No need to process messages sent by bot. If the author is the bot, return
        if msg.author == self.user:
            return

        logger.info(
            f"Received message from {msg.author.name}#{msg.author.discriminator} in channel {msg.channel.name}. Contents: {msg.content}"
        )
        # TODO - See where it makes sense to parse the message and determine course of action. Might be in the discord process in order to free up main process. Depends on whether result is picklable.
        self.pipe_end.send(msg.content)

    async def start(self, *args, **kwargs) -> None:
        """
        Creates a TaskGroup to run the Discord client asynchronously with the listener.
        The discord client listens for any discord events (currently only defined: on_message). It relays these messages to the main process.
        The listener listens for any signals from the main process. It relays these messages to discord.
        """
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                discord.Client.start(self, self.config["DEFAULT"]["DISCORD_TOKEN"])
            )
            tg.create_task(self.relay_in_game_messages_to_discord())

    async def relay_in_game_messages_to_discord(self) -> None:
        """
        This method is responsible for listening to the main process.
        If main process sends a None signal, then it means the process is shutting down and this method will close both the Discord client and the listener.
        Otherwise, the signal is assumed to be a message meant for the user. It is sent to the specified chat channel on Discord.
        :return: None
        """
        while True:
            # Check if a signal is received from main process, blocks Discord Process for 2 seconds, meaning Discord.client is idle during this time.
            if await asyncio.to_thread(self.pipe_end.poll):
                signal = self.pipe_end.recv()
                if signal is None:
                    logger.info("Stopping Discord Communications.")
                    self.pipe_end.close()
                    await self.close()
                    break
                else:
                    logger.info(
                        f"{self.__class__.__name__} received a signal {signal}. Sending to Discord."
                    )
                    await self.get_channel(self.general_chat_id).send(signal)
