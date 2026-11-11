"""
Typing in the chat, the way a person would. These run in Main Process, as the
procedures of `ActionRequest`s.

Both procedures take the same steps:

1. release every key (the character stops), then a short pause;
2. open the channel with its key, then a pause while the chat input opens;
3. for a whisper, type the recipient and confirm it with Enter;
4. type the message;
5. a short pause, then Enter, which sends it;
6. a pause, then Enter again, which closes the chat input, as `write_in_chat`
   has always done.

`reply_in_chat` types at a human `TypingPace`. `write_in_chat` types at
`controller.write`'s own delay, unless its caller passes a pace.

The key that opens each channel is the character's `Chat Keys` binding
(`configs/keybindings.ini`), read by `chat_keys`. A channel it leaves out keeps
the key `write_in_chat` has always pressed.

A bot reads them once, when it is built (`startup_chat_keys`): a malformed
binding refuses the start there, rather than after a failsafe or a Discord
`WRITE`. Its DecisionMakers then take the keys from its `BotData`, and the
Discord parser, in the same process as the bot's build, from
`started_chat_keys`.
"""

import ast
import asyncio
import logging
import random
from collections.abc import Mapping
from configparser import SectionProxy
from types import MappingProxyType
from typing import Any

from botting import controller
from botting.controller import KEYBOARD_MAPPING, TypingPace
from botting.utilities import config_reader

logger = logging.getLogger(__name__)

CHAT_KEYS_OPTION = "Chat Keys"
"""The option of a character's keybindings section that binds the channels."""

DEFAULT_CHAT_KEYS: Mapping[str, str] = MappingProxyType(
    {
        "general": "1",
        "party": "2",
        "buddy": "3",
        "guild": "4",
        "alliance": "5",
        "spouse": "6",
        "whisper": "h",
    }
)
"""Every channel, with the key that opens it unless `Chat Keys` says otherwise."""

WHISPER = "whisper"

# Pauses, in seconds, as (shortest, longest). The spec sets the pause before
# opening the channel and the one before sending. The others are the waits
# `write_in_chat` has always made, kept as the shortest: the chat input may need
# them, and #465 measures the client.
BEFORE_OPENING = (0.3, 0.8)
AFTER_OPENING = (0.5, 0.8)
AFTER_RECIPIENT = (0.25, 0.5)
BEFORE_SENDING = (0.2, 0.5)
BEFORE_CLOSING = (0.25, 0.5)


def chat_keys(ign: str) -> dict[str, str]:
    """
    The key that opens each channel for `ign`, from its keybindings section.
    :param ign: The character, whose section of `configs/keybindings.ini` is read.
    :return: Every channel's key.
    :raises KeyError: When the file has no section for `ign`.
    :raises TypeError: When `Chat Keys` is not a dict.
    :raises ValueError: When it binds an unknown channel, or binds one to no key.
    """
    section = config_reader("keybindings", ign)
    assert isinstance(section, SectionProxy), f"No keybindings section for {ign!r}."
    return read_chat_keys(section.get(CHAT_KEYS_OPTION), ign)


_STARTED: dict[str, Mapping[str, str]] = {}
"""The keys `startup_chat_keys` read, by IGN, in this process."""


def startup_chat_keys(ign: str) -> dict[str, str]:
    """
    `ign`'s chat keys, read once when its bot is built, and kept for
    `started_chat_keys`. A missing keybindings section gives the defaults, as
    writing from Discord always allowed; a malformed binding raises.
    :param ign: The character.
    :return: Every channel's key.
    :raises TypeError: When `Chat Keys` is not a dict.
    :raises ValueError: When it binds an unknown channel, or binds one to no key.
    """
    try:
        keys = chat_keys(ign)
    except AssertionError, KeyError:
        logger.warning(
            "No keybindings section for %r: chatting with the default chat keys.",
            ign,
        )
        keys = dict(DEFAULT_CHAT_KEYS)
    _STARTED[ign] = MappingProxyType(dict(keys))
    return keys


def started_chat_keys(ign: str) -> dict[str, str] | None:
    """The keys `startup_chat_keys` read for `ign` in this process, or `None`
    when no bot of that name was built here."""
    keys = _STARTED.get(ign)
    return None if keys is None else dict(keys)


def read_chat_keys(raw: str | None, ign: str) -> dict[str, str]:
    """
    The key that opens each channel, from a keybindings section's `Chat Keys`.

    It is written like `Non Skill Keys`, as a dict literal:
    `{'general': '1', 'whisper': 'h'}`. A channel it leaves out, or a section
    without it, keeps its key from `DEFAULT_CHAT_KEYS`.
    :param raw: The option's value, or None when the section has none.
    :param ign: The character, to name in an error.
    :return: Every channel's key.
    :raises TypeError: When `raw` is not a dict.
    :raises ValueError: When it binds an unknown channel, or binds one to no key.
    """
    keys = dict(DEFAULT_CHAT_KEYS)
    if raw is None:
        return keys
    where = f"{CHAT_KEYS_OPTION!r} for {ign!r} in configs/keybindings.ini"
    try:
        bound: object = ast.literal_eval(raw)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"{where} is not a dict literal: {exc}") from exc
    if not isinstance(bound, dict):
        raise TypeError(f"{where} must be a dict, not {type(bound).__name__}.")
    unknown = sorted(str(name) for name in bound if name not in DEFAULT_CHAT_KEYS)
    if unknown:
        raise ValueError(
            f"{where} names unknown channels {unknown}; the channels are "
            f"{sorted(DEFAULT_CHAT_KEYS)}."
        )
    for channel, key in bound.items():
        if not isinstance(key, str) or not (len(key) == 1 or key in KEYBOARD_MAPPING):
            raise ValueError(
                f"{where} binds {channel!r} to {key!r}, which is not a key: use one "
                f"character, or a key name such as 'enter'."
            )
        keys[channel] = key
    return keys


async def reply_in_chat(
    handle: int,
    message: str,
    channel: str,
    whisper_to: str | None,
    pace: TypingPace,
    *,
    keys: Mapping[str, str],
) -> None:
    """
    Reply in the chat the way a person would: stop, a short pause, open the
    channel, type at `pace`, a short pause, and send.
    :param handle: The client's window.
    :param message: What to say.
    :param channel: Where to say it: one of `DEFAULT_CHAT_KEYS`.
    :param whisper_to: Who to whisper to, on the whisper channel only.
    :param pace: How fast to type the recipient and the message.
    :param keys: The key that opens each channel: `chat_keys(ign)`. Required, so
        a caller cannot leave the character's own bindings unread.
    :raises ValueError: For an unknown channel, a whisper with no recipient, or a
        recipient on another channel. Nothing is sent.
    """
    if channel == WHISPER and not whisper_to:
        raise ValueError("A whisper needs a recipient.")
    if channel != WHISPER and whisper_to is not None:
        raise ValueError(f"Only a whisper has a recipient, not {channel!r}.")
    await _type_in_chat(
        handle, message, channel, whisper_to, keys, silenced=False, pace=pace
    )


async def write_in_chat(
    handle: int,
    message: str,
    channel: str = "general",
    whisper_to: str | None = None,
    silenced: bool = False,
    keys: Mapping[str, str] | None = None,
    **kwargs: Any,  # noqa: ANN401
) -> None:
    """
    Write in the chat, taking `reply_in_chat`'s steps.
    :param handle: The client's window.
    :param message: What to say.
    :param channel: Where to say it: one of `DEFAULT_CHAT_KEYS`.
    :param whisper_to: Who to whisper to, on the whisper channel. Without one,
        the whisper's recipient is confirmed as it stands.
    :param silenced: Whether to post the keys to the window rather than send them
        to the foreground one.
    :param keys: The key that opens each channel, `chat_keys(ign)`; None uses
        `DEFAULT_CHAT_KEYS`.
    :param kwargs: Passed on to `controller.write`: its `delay`, or a `pace`.
    :raises ValueError: For an unknown channel. Nothing is sent.
    """
    await _type_in_chat(
        handle,
        message,
        channel,
        whisper_to,
        DEFAULT_CHAT_KEYS if keys is None else keys,
        silenced=silenced,
        **kwargs,
    )


async def _type_in_chat(
    handle: int,
    message: str,
    channel: str,
    whisper_to: str | None,
    keys: Mapping[str, str],
    silenced: bool,
    **write_kwargs: Any,  # noqa: ANN401
) -> None:
    """The steps both procedures take; see the module's docstring."""
    if channel not in DEFAULT_CHAT_KEYS:
        raise ValueError(
            f"Channel {channel!r} not recognized; the channels are "
            f"{sorted(DEFAULT_CHAT_KEYS)}."
        )
    key = keys.get(channel, DEFAULT_CHAT_KEYS[channel])

    # Stop whatever the character was doing before typing. This has to happen here,
    # in Main Process, since the requesting DecisionMaker may not send input itself.
    controller.release_all(handle)
    await _pause(BEFORE_OPENING)
    await controller.press(handle, key, silenced=silenced)
    await _pause(AFTER_OPENING)

    if channel == WHISPER:
        if whisper_to is not None:
            await controller.write(
                handle, whisper_to, silenced=silenced, **write_kwargs
            )
            await _pause(AFTER_RECIPIENT)
        await controller.press(handle, "enter", silenced=silenced)
        await _pause(AFTER_RECIPIENT)

    await controller.write(handle, message, silenced=silenced, **write_kwargs)
    await _pause(BEFORE_SENDING)
    await controller.press(handle, "enter", silenced=silenced)
    await _pause(BEFORE_CLOSING)
    await controller.press(handle, "enter", silenced=silenced)


async def _pause(bounds: tuple[float, float]) -> None:
    """Wait a random time within `bounds`, in seconds."""
    await asyncio.sleep(random.uniform(*bounds))
