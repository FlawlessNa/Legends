import logging
import multiprocessing.connection

from functools import partial
from typing import Optional

from ..bot import BotLauncher

logger = logging.getLogger(__name__)


def message_parser(
    message: str, main_pipe: multiprocessing.connection.Connection
) -> Optional[callable]:
    """
    Message Parsing is made inside the Main Process. This way, the returned actions are not required to be picklable (e.g. transferable between processes).
    Supported commands:
    - kill: Stops everything, closes all clients, and stops program execution.
    - pause: Pauses all bots, but keeps everything else running. The bots remain idle and in-place wherever they are.
        Options: -t <time> - The time, in seconds, to pause for. If not provided, the bots will remain paused until resumed.
    - resume: Can be used after a pause or a stop to resume.
    - stop: Stops all bots and send them to Lounge. Does not close clients. Does not stop program execution. When resumed, the bots are all re-initialized.
    - write: Writes a message to the chat. When this option is used, the 2nd word in the message is the IGN of the character that will write the message.
        Options: -a: All Chat (default)
                 -h: Whisper chat (responding to last whisper)

    :param message: The message to parse, received from Discord and written by user. The first word should always be the command to perform.
    :param main_pipe: The end of the Pipe object that connects main process to the child.
    :return: If True, the loop relaying messages from Discord to the main process will be stopped.
    """

    supported_commands = ["kill", "pause", "resume", "stop", "write"]

    # Command is always the first word
    command = message.lower().split(" ")[0]

    match command:
        case "kill":
            # TODO - Close clients as well?
            logger.info("Received KILL signal from Discord. Stopping all bots.")
            return BotLauncher.cancel_all
        case "pause":
            pass
        case "resume":
            pass
        case "stop":
            pass
        case "write":
            pass
        case _:
            return partial(main_pipe.send, f"Command {command} not recognized.")
