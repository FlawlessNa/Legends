import argparse
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.NOTSET


class BaseParser(ABC):
    """
    # TODO - Implement Discord confirmation and/or error message from user-input.
     (EG: if input is wrong, send a discord message to inform user. If input is correct,
     send confirmation to user).
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
    action_choices = ['KILL', 'PAUSE', 'RESUME', 'WRITE']
    action_choices.extend(action.lower() for action in action_choices)
    action_choices.extend(action.title() for action in action_choices)

    def __init__(self) -> None:
        self.parser = argparse.ArgumentParser(
            description='Parse messages from discord user.',
            exit_on_error=False
        )
        self.parser.add_argument(
            'action',
            type=str,
            help='The action to perform.',
            choices=self.action_choices,
        )
        self.parser.add_argument(
            '--ign',
            type=str,
            help='The IGN of the bot to perform the action on.',
            required=False,
            nargs='+'
        )
        self.parser.add_argument(
            '-m', '--message',
            type=str,
            help='The message to write.',
            nargs='+',
            required=False,
        )

    def parse_message(self, message: str):
        """
        Parses a message from the user and fires the appropriate actions.
        :param message: The message to parse.
        :return: TBD.
        """
        args = self.parser.parse_args(message.split())
        action = args.action.upper()

        if action == 'KILL':
            if args.ign or args.message:
                logger.warning(
                    "KILL action does not accept --ign or --message arguments. "
                    "They will be ignored."
                )
            return self.kill()

        elif action == 'PAUSE':
            if args.message:
                logger.warning(
                    "PAUSE action does not accept --message argument. "
                    "It will be ignored."
                )
            return self.pause(args.ign)

        elif action == 'RESUME':
            if args.message:
                logger.warning(
                    "RESUME action does not accept --message argument. "
                    "It will be ignored."
                )
            return self.resume(args.ign)

        elif action == 'WRITE':
            if not args.message:
                logger.error(
                    "WRITE action requires a --message argument. "
                    "Please provide one."
                )
                return
            return self.write(' '.join(args.message), args.ign)
        else:
            raise ValueError(f"Invalid action: {action}")

    @abstractmethod
    def kill(self):
        """
        Called from the MainProcess. Should kill all bots and stop process.
        :return: TBD
        """
        pass

    @abstractmethod
    def pause(self, who: list[str] = None):
        """
        Called from the MainProcess. Should pause all bots or a specific bot.
        :param who: The bot to pause. If None, pauses all bots.
        :return: TBD
        """
        pass

    @abstractmethod
    def resume(self, who: list[str] = None):
        """
        Called from the MainProcess. Should resume all bots or a specific bot.
        :param who: The bot to resume. If None, resumes all bots.
        :return: TBD
        """
        pass

    @abstractmethod
    def write(self, message: str, who: str = None):
        """
        Called from the MainProcess. Should write a message to a specific bot.
        :param message: The message to write.
        :param who: The bot that should write the message. If None, the "Main" bot
        writes the message.
        :return: TBD
        """
        pass
