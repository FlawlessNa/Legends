import asyncio
import logging

from functools import partial
from typing import Optional

from botting.core import QueueAction, GeneratorUpdate, DecisionGenerator
from royals.actions import write_in_chat


logger = logging.getLogger(__name__)


def single_bot_parser(message: str, bots: list) -> Optional[QueueAction]:
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
    :param bots: The list of bots that are currently running.
    :return: If True, the loop relaying messages from Discord to the main process will be stopped.
    """

    supported_commands = ["kill", "pause", "resume", "stop", "write", "hold"]
    assert len(bots) == 1, "This parser is only meant to be used with a single bot."

    # Command is always the first word
    command = message.lower().split(" ")[0]

    match command:
        case "kill":
            return None
        case "pause":
            pass
        case "resume":
            return QueueAction(
                identifier="Resuming",
                priority=0,
                action=partial(asyncio.sleep, 0),
                user_message=["Resuming all bots"],
                update_generators=GeneratorUpdate(
                    generator_id=0,
                    generator_kwargs={"blocked": False},
                ),
            )
        case "stop":
            pass
        case "write":
            chat_type = message.lower().split(" ")[1]
            if chat_type in ["general", "whisper"]:
                txt_to_write = message.lower().split(" ")[2:]
            else:
                chat_type = "general"
                txt_to_write = message.lower().split(" ")[1:]
            return QueueAction(
                identifier="Writing to chat",
                priority=0,
                action=partial(
                    write_in_chat,
                    handle=bots[0].handle,
                    message=" ".join(txt_to_write),
                    channel=chat_type,
                ),  # TODO - Add callback to validate message was written
            )
        case "hold":
            return QueueAction(
                identifier="Hold",
                priority=0,
                action=partial(asyncio.sleep, 0),
                user_message=["All bots now on hold"],
                update_generators=GeneratorUpdate(
                    generator_id=0,
                    generator_kwargs={"blocked": True},
                ),
            )

        case _:
            return QueueAction(
                identifier="Unknown Discord Command",
                priority=0,
                action=partial(asyncio.sleep, 0),
                user_message=[f"Command {command} not recognized."],
            )
