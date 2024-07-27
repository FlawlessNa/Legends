import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)
LOG_LEVEL = logging.DEBUG


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

    def parse_message(self, message: str):
        """
        Parses a message from the user and fires the appropriate actions.
        :param message: The message to parse.
        :return: TBD.
        """
        lst = message.split(" ")
        action = lst[0]
        if action.upper() == 'KILL':
            return self.kill()
        elif action.upper() == 'PAUSE':
            if '--ign' in lst:
                who = lst[lst.index('--ign') + 1:]
            else:
                who = None
            return self.pause(who)
        elif action.upper() == 'RESUME':
            if '--ign' in lst:
                who = lst[lst.index('--ign') + 1:]
            else:
                who = None
            return self.resume(who)
        elif action.upper() == 'WRITE':
            if '--ign' in lst:
                who = lst[lst.index('--ign') + 1]
            else:
                who = None
            message = ' '.join(lst[lst.index('--m') + 1:])
            return self.write(message, who)
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
