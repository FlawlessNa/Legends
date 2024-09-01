import asyncio
import cv2
import discord
import logging
import multiprocessing.connection
import numpy as np
import os

from functools import cached_property

from botting.utilities import config_reader

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.DEBUG


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
        self.config = config_reader("discord")
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

    async def on_ready(self) -> None:
        """
        Callback function triggered by discord.Client when connection is established.
        """
        msg = f"Discord Communication Established with {self.user}."
        logger.info(msg)
        await self.get_channel(self.chat_id).send(msg)

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
            f"Received message from {msg.author.name}#{msg.author.discriminator} in "
            f"channel {msg.channel.name}. Contents: {msg.content}"
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
                        await self.get_channel(self.chat_id).send(
                            f"Discord Communication Stopped with {self.user}"
                        )
                        logger.info("Stopping Discord Communications.")
                        break
                    else:
                        if isinstance(signal, str):
                            logger.info(
                                f"{self.__class__.__name__} received a signal {signal}"
                                f". Sending to Discord."
                            )
                            msg = (
                                f'<@{self.config[self.config_section]["DISCORD_ID"]}'
                                f"> {signal}"
                            )
                            await self.get_channel(self.chat_id).send(msg)
                        elif isinstance(signal, np.ndarray):
                            cv2.imwrite("temp.png", signal)
                            with open("temp.png", "rb") as f:
                                await self.get_channel(self.chat_id).send(
                                    file=discord.File(f)
                                )
                            # Now delete the file
                            os.remove("temp.png")

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
