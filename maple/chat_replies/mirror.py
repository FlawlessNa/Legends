"""
The Discord mirror: each exchange, as the maintainer reads it while it happens.

An exchange is one `Burst` and what became of it: `[whisper] Bob: hi u there? →
ya`, or `→ (silent)` when the model chose to say nothing. A GM's line, and the
reply it got, start with the maintainer's mention, so they ring.

While automatic replies are off, a line that would have been answered is posted
on its own, as it is read: `[whisper] Bob: hi → (replies off)`.

`mirror` sends through whatever `send` the caller gives it: an Engine process
reaches Discord by sending a string down its pipe, which Main Process forwards.
"""

import logging
from collections.abc import Callable
from configparser import ConfigParser

from botting.communications.messages import QuietMessage
from botting.utilities import config_reader

from .addressing import Address
from .conversation import Burst, Entry
from .relay import Failed, RelayOutcome, Reply, Silent

logger = logging.getLogger(__name__)

#: What an exchange's lines are joined with when a player said several.
LINE_JOIN = " / "


def format_exchange(
    burst: Burst, outcome: RelayOutcome, mention: str | None = None
) -> str:
    """
    One exchange as one Discord message.

    :param mention: The maintainer's mention, e.g. ``<@123>``. Put in front of a
        GM exchange; ``None`` leaves it out.
    """
    match outcome:
        case Reply(text):
            result = text
        case Silent():
            result = "(silent)"
        case Failed(reason):
            result = f"(no reply: {reason})"
    return _format(burst, result, mention)


def format_unanswered(entry: Entry, mention: str | None = None) -> str:
    """
    One line read while automatic replies are off, as one Discord message.

    :param mention: As for `format_exchange`.
    """
    return _format(_alone(entry), REPLIES_OFF, mention)


#: What a line read while automatic replies are off came to.
REPLIES_OFF = "(replies off)"


def _alone(entry: Entry) -> Burst:
    return Burst(entry.speaker, entry.kind, entry.address, (entry,))


def _format(burst: Burst, result: str, mention: str | None) -> str:
    said = LINE_JOIN.join(e.message or "?" for e in burst.entries)
    line = f"[{burst.channel.value}] {burst.speaker or '?'}: {said} → {result}"
    if burst.address is Address.GM and mention:
        return f"{mention} {line}"
    return line


def mirror(
    send: Callable[[str], object],
    burst: Burst,
    outcome: RelayOutcome,
    mention: str | None = None,
) -> None:
    """
    Post one exchange to Discord through `send`. A GM exchange rings the
    maintainer; every other one is posted quietly.
    """
    text = format_exchange(burst, outcome, mention)
    send(text if burst.address is Address.GM else QuietMessage(text))


def mirror_unanswered(
    send: Callable[[str], object], entry: Entry, mention: str | None = None
) -> None:
    """Post one line read while automatic replies are off, through `send`. A GM's
    rings the maintainer; every other one is posted quietly."""
    text = format_unanswered(entry, mention)
    send(text if entry.address is Address.GM else QuietMessage(text))


def discord_mention() -> str | None:
    """
    The maintainer's mention, from the Discord config: ``<@DISCORD_ID>``. `None`
    when Discord isn't configured, so a session without it still runs.
    """
    try:
        config = config_reader("discord")
        assert isinstance(config, ConfigParser), "Expected the whole discord config."
        section = f"User {config['DEFAULT']['user']}"
        return f"<@{config[section]['DISCORD_ID']}>"
    except AssertionError, KeyError:
        logger.info("Discord is not configured: the mirror will not mention anyone.")
        return None
