"""
A Bot's data with its Bot-level Providers, built as `Bot.child_init` and
`MapleBot.child_init` build them, from stand-ins: no client, no sprites.

The client shows whatever `frames` returns, one call per capture. The screen
readers are the test's own, by `ScreenReadersProvider`'s keywords (`chat=`,
`buffs=`...). Assembly then builds whatever else a DecisionMaker reads, as it
does for a Bot: `assemble(served, SomeDecisionMaker)`.
"""

import queue
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from botting.core import (
    BotData,
    DecisionMaker,
    Providers,
    RepliesProvider,
    WindowProvider,
)
from botting.core.data_keys import resolve_providers
from botting.screen import capture
from maple.decision_makers.providers import (
    CharacterProvider,
    ClientProvider,
    ScreenReadersProvider,
)


class Client:
    """The client's capture: each grab shows what `frames` returns."""

    def __init__(self, frames: Callable[[], object]) -> None:
        self.frames = frames
        self.grabs = 0

    def grab(self, handle: int) -> object:
        self.grabs += 1
        return self.frames()


class Proxies:
    """Main Process's proxies, made here: a Condition is a thread's, a Queue a
    thread-safe queue's."""

    def instance(self, key: str, primitive_type: str) -> object:
        if primitive_type == "Queue":
            return queue.Queue()
        return getattr(threading, primitive_type)()


@dataclass
class Served:
    """What `serve` built."""

    data: BotData
    providers: Providers
    client: Client
    #: The replies switch, as `Bot.replies` switches it.
    replies: RepliesProvider
    pipe: Any = field(default=None)


def serve(
    monkeypatch: pytest.MonkeyPatch,
    ign: str = "Bot",
    *,
    pipe: Any = None,  # noqa: ANN401 - whatever records what is sent
    proxies: Any = None,  # noqa: ANN401 - a ProxyFactory, or a stand-in
    data: BotData | None = None,
    frames: Callable[[], object] = lambda: None,
    handle: int = 1,
    chat_keys: Mapping[str, str] | None = None,
    character: object = None,
    buff_names: tuple[str, ...] = (),
    **readers: object,
) -> Served:
    """
    `ign`'s data, with the window, the replies switch, the screen readers, the
    character when one is given, and the client's frame and chat keys.

    :param frames: What the client shows, one call per capture.
    :param character: What `CHARACTER` serves; none is served without one.
    :param readers: The screen readers, by `ScreenReadersProvider`'s keywords.
    """
    client = Client(frames)
    monkeypatch.setattr(capture, "_source", client)
    data = data or BotData(ign)
    providers = Providers(data, pipe, proxies or Proxies(), {})  # pyright: ignore[reportArgumentType] - a stand-in
    providers.add(WindowProvider, handle=handle)
    replies = providers.add(RepliesProvider)
    assert isinstance(replies, RepliesProvider)
    providers.add(ScreenReadersProvider, sprites=None, **readers)
    if character is not None:
        providers.add(
            CharacterProvider,
            character_class=lambda *_: character,
            buff_names=buff_names,
        )
    providers.add(ClientProvider, chat_keys=dict(chat_keys or {}))
    return Served(data, providers, client, replies, pipe)


def assemble(served: Served, *classes: type[DecisionMaker]) -> None:
    """Build the Providers `classes` read, as assembly does."""
    served.providers.build(resolve_providers(classes))
