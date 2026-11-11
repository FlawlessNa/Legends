"""
The Discord mirror: each exchange, as the maintainer reads it while it happens.

An exchange is one `Burst` and what became of it: `[whisper] Bob: hi u there? →
ya`, or `→ (silent)` when the model chose to say nothing. A GM's line, and the
reply it got, start with the maintainer's mention, so they ring.

`mirror` sends through whatever `send` the caller gives it: an Engine process
reaches Discord by sending a string down its pipe, which Main Process forwards.
"""

import logging
from collections.abc import Callable
from configparser import ConfigParser

from botting.utilities import config_reader

from .addressing import Address
from .conversation import Burst
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
    said = LINE_JOIN.join(e.message or "?" for e in burst.entries)
    match outcome:
        case Reply(text):
            result = text
        case Silent():
            result = "(silent)"
        case Failed(reason):
            result = f"(no reply: {reason})"
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
    """Post one exchange to Discord through `send`."""
    send(format_exchange(burst, outcome, mention))


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
