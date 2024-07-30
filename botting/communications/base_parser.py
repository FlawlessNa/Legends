import argparse
import logging
import multiprocessing.connection

from abc import ABC, abstractmethod
from enum import Enum
from functools import cached_property
from botting.core.botv2.action_data import ActionRequest

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.NOTSET


class Actions(Enum):
    KILL = "KILL"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    WRITE = "WRITE"


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
    """

    action_choices = [action.value for action in Actions]
    action_choices.extend(action.value.lower() for action in Actions)
    action_choices.extend(action.value.title() for action in Actions)

    def __init__(self, pipe: multiprocessing.connection.Connection) -> None:
        self.pipe = pipe

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
            "--ign",
            type=str,
            help="The IGN of the bot to perform the action on.",
            required=False,
            nargs="+",
        )
        parser.add_argument(
            "-m",
            "--message",
            type=str,
            help="The message to write.",
            nargs="+",
            required=False,
        )
        return parser

    def parse_message(self, message: str) -> ActionRequest | None:
        """
        Parses a message from the user and fires the appropriate actions.
        :param message: The message to parse.
        :return: TBD.
        """
        try:
            args = self.parser.parse_args(message.split())
        except argparse.ArgumentError as e:
            self.pipe.send(f"{e}")
            return
        except Exception as e:
            raise

        action = args.action.upper()

        if action == "KILL":
            if args.ign or args.message:
                msg = (
                    "KILL action does not accept --ign or --message arguments. "
                    "They will be ignored."
                )
                logger.warning(msg)
                self.pipe.send(msg)
            request = self.kill()

        elif action == "PAUSE":
            if args.message:
                msg = (
                    "PAUSE action does not accept --message argument. "
                    "It will be ignored."
                )
                logger.warning(msg)
                self.pipe.send(msg)
            request = self.pause(args.ign)

        elif action == "RESUME":
            if args.message:
                msg = (
                    "RESUME action does not accept --message argument. "
                    "It will be ignored."
                )
                logger.warning(msg)
                self.pipe.send(msg)
            request = self.resume(args.ign)

        elif action == "WRITE":
            if not args.message:
                msg = (
                    "WRITE action requires a --message argument. " "Please provide one."
                )
                logger.error(msg)
                self.pipe.send(msg)
                return
            request = self.write(" ".join(args.message), args.ign)
        else:
            raise ValueError(f"Invalid action: {action}")

        self.pipe.send(f"Confirmation: Executing {request}")
        return request

    @abstractmethod
    def kill(self) -> ActionRequest:
        """
        Called from the MainProcess. Should kill all bots and stop process.
        :return: TBD
        """
        pass

    @abstractmethod
    def pause(self, who: list[str] = None) -> ActionRequest:
        """
        Called from the MainProcess. Should pause all bots or a specific bot.
        :param who: The bot to pause. If None, pauses all bots.
        :return: TBD
        """
        pass

    @abstractmethod
    def resume(self, who: list[str] = None) -> ActionRequest:
        """
        Called from the MainProcess. Should resume all bots or a specific bot.
        :param who: The bot to resume. If None, resumes all bots.
        :return: TBD
        """
        pass

    @abstractmethod
    def write(self, message: str, who: str = None) -> ActionRequest:
        """
        Called from the MainProcess. Should write a message to a specific bot.
        :param message: The message to write.
        :param who: The bot that should write the message. If None, the "Main" bot
        writes the message.
        :return: TBD
        """
        pass
