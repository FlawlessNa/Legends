import asyncio
import discord
import logging
import multiprocessing.connection

from functools import cached_property

from royals.utilities import ChildProcess, config_reader

logger = logging.getLogger(__name__)


class DiscordComm(discord.Client, ChildProcess):
    """Establishes communication with Discord, while maintaining the end of a Pipe object to communicate with the main process."""

    def __init__(self, pipe_end: multiprocessing.connection.Connection) -> None:
        super().__init__(intents=discord.Intents.all())
        self.config = config_reader("discord")
        ChildProcess.__init__(self, pipe_end)

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

    async def connect_and_listen(self) -> None:
        """
        Creates a TaskGroup to run the Discord client asynchronously with the listener.
        The discord client listens for any discord events (currently only defined: on_message). It relays these messages to the main process.
        The listener listens for any signals from the main process. It relays these messages to discord.
        """
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.start(self.config["DEFAULT"]["DISCORD_TOKEN"]))
            tg.create_task(self.listener())

    async def listener(self) -> None:
        """
        This method is responsible for listening to the main process.
        If main process sends a None signal, then it means the process is shutting down and this method will close both the Discord client and the listener.
        Otherwise, the signal is assumed to be a message meant for the user. It is sent to the specified chat channel on Discord.
        :return: None
        """
        while True:
            # Check if a signal is received from main process, blocks Discord Process for 2 seconds, meaning Discord.client is idle during this time.
            if self.pipe_end.poll(2):
                signal = self.pipe_end.recv()
                if signal is None:
                    logger.info("Stopping Discord Communications.")
                    await self.close()
                    break
                else:
                    logger.debug(
                        f"{self.__class__.__name__} received a signal {signal}. Sending to Discord."
                    )
                    await self.get_channel(self.general_chat_id).send(signal)
            # Here it's the opposite. The listener is idle while Discord.client is able to retrieve messages.
            await asyncio.sleep(2)
