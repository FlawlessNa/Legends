import asyncio
import io
import logging
import multiprocessing.connection
from configparser import ConfigParser
from functools import cached_property

import cv2
import discord
import numpy as np

from botting.utilities import config_reader

logger = logging.getLogger(__name__)


class DiscordIO(discord.Client):
    """
    Establishes communication with Discord,
    while maintaining the end of a Pipe object to communicate with the main process.
    """

    def __init__(
        self,
        pipe: multiprocessing.connection.Connection,
    ) -> None:
        super().__init__(intents=discord.Intents.all())
        config = config_reader("discord")
        # One argument means the whole file; the union is for the narrower calls.
        assert isinstance(config, ConfigParser), (
            "Expected the whole discord config, not a section."
        )
        self.config = config
        self.config_section = f"User {self.config['DEFAULT']['user']}"
        self.pipe = pipe

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

    @property
    def channel(self) -> discord.TextChannel:
        """
        The one text channel this Session talks through.

        `get_channel` returns any channel kind or None, and most of those have
        no `send`. `chat_id` already selected a text channel, so anything else
        here means the channel was deleted or the id went stale mid-session -
        worth a clear error rather than an AttributeError on a ForumChannel.
        """
        channel = self.get_channel(self.chat_id)
        if not isinstance(channel, discord.TextChannel):
            raise TypeError(
                f"Discord channel {self.chat_id} is {type(channel).__name__}, "
                f"not a text channel."
            )
        return channel

    async def on_ready(self) -> None:
        """
        Callback function triggered by discord.Client when connection is established.
        """
        msg = f"Discord Communication Established with {self.user}."
        logger.info(msg)
        await self.channel.send(msg)

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
        if msg.author == self.user or (
            msg.author.id != int(self.config[self.config_section]["DISCORD_ID"])
            or getattr(msg.channel, "name", None)
            != self.config[self.config_section]["DISCORD_CHANNEL"]
        ):
            return

        logger.info(
            "Received message from %s#%s in channel %s. Contents: %s",
            msg.author.name,
            msg.author.discriminator,
            getattr(msg.channel, "name", "<unnamed>"),
            msg.content,
        )
        self.pipe.send(msg.content)  # Send message to main process for parsing

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
        try:
            while True:
                # Check if a signal is received from main process
                if await asyncio.to_thread(self.pipe.poll):
                    signal = self.pipe.recv()
                    if signal is None:
                        await self.channel.send(
                            f"Discord Communication Stopped with {self.user}"
                        )
                        logger.info("Stopping Discord Communications.")
                        break
                    else:
                        if isinstance(signal, str):
                            logger.info(
                                "%s received a signal %s. Sending to Discord.",
                                self.__class__.__name__,
                                signal,
                            )
                            msg = (
                                f"<@{self.config[self.config_section]['DISCORD_ID']}"
                                f"> {signal}"
                            )
                            await self.channel.send(msg)
                        elif isinstance(signal, np.ndarray):
                            # Encoded in memory rather than through a temp file:
                            # `open` blocks the event loop, and every send used
                            # the same "temp.png", so two overlapping sends
                            # raced over one path.
                            _, buffer = cv2.imencode(".png", signal)
                            await self.channel.send(
                                file=discord.File(
                                    io.BytesIO(buffer.tobytes()),
                                    filename="screenshot.png",
                                )
                            )

                        else:
                            raise NotImplementedError
        finally:
            if not self.pipe.closed:
                logger.debug("Closing Peripherals pipe to main process.")
                self.pipe.send(None)
                self.pipe.close()

            if not self.is_closed():
                logger.debug("Closing Discord Client.")
                await self.close()
