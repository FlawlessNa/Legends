import argparse
import logging
import multiprocessing.connection
from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property
from typing import ClassVar

from botting.core.action_data import ActionRequest, DiscordRequest

logger = logging.getLogger(__name__)


class Actions(Enum):
    KILL = "KILL"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    WRITE = "WRITE"
    REPLIES = "REPLIES"


class BaseParser(ABC):
    """
    Implements basic to interpret discord messages received by the user.
    User messages should have the general format:
    <ACTION> --ign <IGN> (optional) --args <ARGS> (varies based on ACTION)
    Valid Examples:
    KILL
    PAUSE --ign IgnFromARunningBot
    PAUSE --ign IgnFromARunningBot1 IgnFromARunningBot2
    RESUME --ign IgnFromAPausedBot
    WRITE --ign IgnFromABot --m Message to write
    WRITE -ign IgnFromABot -to SomePlayer -m Message to whisper
    WRITE -ign IgnFromABot -channel party -m Message to the party
    REPLIES OFF -ign IgnFromABot
    REPLIES ON

    ``REPLIES`` declares one argument, ``ON`` or ``OFF``, right after the action.
    A ``WRITE`` stops the automatic replies of the bot it writes through.
    """

    #: The channels a ``WRITE`` can name. A whisper is named by ``-to`` instead.
    write_channels: ClassVar[tuple[str, ...]] = ("general", "party", "buddy")

    action_choices: ClassVar[list[str]] = [action.value for action in Actions]
    action_choices.extend(action.value.lower() for action in Actions)
    action_choices.extend(action.value.title() for action in Actions)

    def __init__(self, pipe: multiprocessing.connection.Connection) -> None:
        self.pipe = pipe
        self.main_ign: str | None = None

    @cached_property
    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(
            description="Parse messages from discord user.", exit_on_error=False
        )
        parser.add_argument(
            "action",
            type=str,
            help="The action to perform.",
            choices=self.action_choices,
        )
        parser.add_argument(
            "-ign",
            type=str,
            help="The IGN of the bot to perform the action on.",
            required=False,
            nargs="+",
        )
        parser.add_argument(
            "-message",
            "-m",
            type=str,
            help="The message to write.",
            nargs="+",
            required=False,
        )
        parser.add_argument(
            "-to",
            type=str,
            help="The player to whisper the message to.",
            required=False,
        )
        parser.add_argument(
            "-channel",
            type=str,
            help="The chat channel to write on.",
            required=False,
            choices=self.write_channels,
        )
        parser.add_argument(
            "positional_message",
            type=str,
            help="The message to write (positional argument).",
            nargs="*",
            default=None,
        )
        return parser

    def parse_message(
        self, message: str
    ) -> ActionRequest | str | list[ActionRequest | str] | None:
        """
        Parses a message from the user and fires the appropriate actions.
        :param message: The message to parse.
        :return: What the Main Process must do: an ActionRequest to run, a string
            to dispatch to every Engine, or a list of those, in order. ``None``
            when the message is not valid.
        """
        try:
            args = self.parser.parse_args(message.split())
        except argparse.ArgumentError as e:
            self.pipe.send(f"{e}")
            return
        except Exception:
            raise

        action = args.action.upper()

        if action == "KILL":
            if args.ign or args.message or args.positional_message:
                msg = (
                    "KILL action does not accept --ign or --message arguments. "
                    "They will be ignored."
                )
                logger.warning(msg)
                self.pipe.send(msg)
            request = self.kill()

        elif action == "PAUSE":
            if args.message or args.positional_message:
                msg = (
                    "PAUSE action does not accept --message argument. "
                    "It will be ignored."
                )
                logger.warning(msg)
                self.pipe.send(msg)
            request = self.pause(args.ign)

        elif action == "RESUME":
            if args.message or args.positional_message:
                msg = (
                    "RESUME action does not accept --message argument. "
                    "It will be ignored."
                )
                logger.warning(msg)
                self.pipe.send(msg)
            request = self.resume(args.ign)

        elif action == "REPLIES":
            if (
                args.message
                or (args.positional_message or [])[1:]
                or args.to
                or args.channel
            ):
                msg = "REPLIES action only accepts ON or OFF, and -ign."
                logger.warning(msg)
                self.pipe.send(msg)
                return
            switch = (args.positional_message or [""])[0].upper()
            if switch not in ("ON", "OFF"):
                msg = "REPLIES action requires ON or OFF right after it."
                logger.warning(msg)
                self.pipe.send(msg)
                return
            request = self.replies(switch == "ON", args.ign)

        elif action == "WRITE":
            if args.to and args.channel:
                msg = "WRITE accepts -to (a whisper) or -channel, not both."
                logger.warning(msg)
                self.pipe.send(msg)
                return
            if not args.message and not args.positional_message:
                msg = "WRITE action requires a --message argument. Please provide one."
                logger.warning(msg)
                self.pipe.send(msg)
                return
            if args.ign is None:
                ign = self.main_ign
                self.pipe.send(
                    f"No --ign argument provided. Writing to {ign} by default, which was"
                    f"the first bot defined within this Session."
                )
            else:
                if len(args.ign) > 1:
                    msg = (
                        f"WRITE action only accepts one -ign argument. "
                        f"Please provide only one, {args.ign} is not valid."
                    )
                    logger.warning(msg)
                    self.pipe.send(msg)
                    return
                ign = args.ign[0]
            if ign is None:
                msg = (
                    "WRITE action needs an -ign: no bot is defined to write by default."
                )
                logger.warning(msg)
                self.pipe.send(msg)
                return
            content = args.message or args.positional_message
            request = [
                self.takeover(ign),
                self.write(" ".join(content), ign, to=args.to, channel=args.channel),
            ]
        else:
            raise ValueError(f"Invalid action: {action}")

        for item in request if isinstance(request, list) else [request]:
            self.pipe.send(
                f"Confirmation that '{getattr(item, 'identifier', item)}' was "
                f"requested by user"
            )
        return request

    @staticmethod
    def replies(on: bool, who: list[str] | None = None) -> str:
        """
        The command string that hands automatic replies back (``on``) or stops
        them, for ``who`` or every bot. ``ON``/``OFF`` is the one argument the
        command declares, so it comes right after the action.
        """
        return f"REPLIES {'ON' if on else 'OFF'} {' '.join(who or ['All'])}"

    @staticmethod
    def takeover(who: str) -> str:
        """
        The command string a ``WRITE`` sends ahead of itself: the maintainer is
        typing for ``who``, so its automatic replies stop. Same effect as
        ``REPLIES OFF``, reported as coming from the write.
        """
        return f"TAKEOVER {who}"

    @staticmethod
    def _kill() -> None:
        raise KeyboardInterrupt("Kill request from Discord confirmed")

    def kill(self) -> ActionRequest:
        """
        Called from the MainProcess. Should kill all bots and stop process.
        :return: An ActionRequest for Main Process to run, or a string to
            dispatch to every Engine.
        """
        return ActionRequest(
            "Killing all tasks",
            self._kill,
            ign="All",
            priority=999,
            block_lower_priority=True,
            discord_request=DiscordRequest("Kill request from Discord confirmed"),
        )

    @abstractmethod
    def pause(self, who: list[str] | None = None) -> ActionRequest | str:
        """
        Called from the MainProcess. Should pause all bots or a specific bot.
        :param who: The bot to pause. If None, pauses all bots.
        :return: An ActionRequest for Main Process to run, or a string to
            dispatch to every Engine.
        """

    @abstractmethod
    def resume(self, who: list[str] | None = None) -> ActionRequest | str:
        """
        Called from the MainProcess. Should resume all bots or a specific bot.
        :param who: The bot to resume. If None, resumes all bots.
        :return: An ActionRequest for Main Process to run, or a string to
            dispatch to every Engine.
        """

    @abstractmethod
    def write(
        self,
        message: str,
        who: str | None = None,
        *,
        to: str | None = None,
        channel: str | None = None,
    ) -> ActionRequest | str:
        """
        Called from the MainProcess. Should write a message to a specific bot.
        :param message: The message to write.
        :param who: The bot that should write the message. If None, the "Main" bot
        writes the message.
        :param to: A player to whisper the message to. Takes the whisper channel.
        :param channel: The channel to write on; general when neither is given.
        :return: An ActionRequest for Main Process to run, or a string to
            dispatch to every Engine.
        """
