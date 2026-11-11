"""
The Discord commands `REPLIES OFF|ON` and `WRITE -to/-channel`: how the parser
reads them, and how an Engine carries them out on its Bots.
"""

import asyncio
import multiprocessing

import pytest

from botting.communications import BaseParser
from botting.core.action_data import ActionRequest
from botting.core.engine import Engine, _ChildProcessEngine  # pyright: ignore[reportPrivateUsage]


class _Pipe:
    def __init__(self) -> None:
        self.sent: list[object] = []

    def send(self, item: object) -> None:
        self.sent.append(item)


class _Parser(BaseParser):
    def pause(self, who: list[str] | None = None) -> str:
        return f"PAUSE {' '.join(who or ['All'])}"

    def resume(self, who: list[str] | None = None) -> str:
        return f"RESUME {' '.join(who or ['All'])}"

    def write(
        self,
        message: str,
        who: str | None = None,
        *,
        to: str | None = None,
        channel: str | None = None,
    ) -> ActionRequest | str:
        return f"WROTE {who} {to} {channel} {message}"


@pytest.fixture
def parser() -> _Parser:
    result = _Parser(_Pipe())  # pyright: ignore[reportArgumentType]
    result.main_ign = "Alice"
    return result


def test_replies_off_names_the_bots_after_its_argument(parser: _Parser) -> None:
    assert parser.parse_message("REPLIES OFF -ign Alice Bob") == "REPLIES OFF Alice Bob"


def test_replies_on_without_an_ign_is_for_every_bot(parser: _Parser) -> None:
    assert parser.parse_message("replies on") == "REPLIES ON All"


def test_replies_needs_on_or_off(parser: _Parser) -> None:
    assert parser.parse_message("REPLIES -ign Alice") is None
    assert parser.parse_message("REPLIES maybe -ign Alice") is None
    assert parser.parse_message("REPLIES") is None


def test_write_whispers_with_to_and_takes_the_replies_over_first(
    parser: _Parser,
) -> None:
    result = parser.parse_message("WRITE -ign Alice -to Bob -m hello there")

    assert result == ["TAKEOVER Alice", "WROTE Alice Bob None hello there"]


def test_write_on_a_channel(parser: _Parser) -> None:
    result = parser.parse_message("WRITE -ign Alice -channel party -m hi all")

    assert result == ["TAKEOVER Alice", "WROTE Alice None party hi all"]


def test_a_plain_write_still_writes_and_now_takes_over(parser: _Parser) -> None:
    result = parser.parse_message("WRITE -ign Alice -m hello")

    assert result == ["TAKEOVER Alice", "WROTE Alice None None hello"]


def test_write_refuses_a_whisper_on_a_channel(parser: _Parser) -> None:
    assert parser.parse_message("WRITE -ign Alice -to Bob -channel party hi") is None


def test_write_refuses_a_channel_it_does_not_have(parser: _Parser) -> None:
    assert parser.parse_message("WRITE -ign Alice -channel guild hi") is None


def test_pause_resume_and_kill_keep_their_form(parser: _Parser) -> None:
    assert parser.parse_message("PAUSE -ign Alice Bob") == "PAUSE Alice Bob"
    assert parser.parse_message("RESUME") == "RESUME All"
    assert isinstance(parser.parse_message("KILL"), ActionRequest)


class _Bot:
    def __init__(self, ign: str) -> None:
        self.ign = ign
        self.calls: list[tuple[str, dict[str, object]]] = []

    def pause(self) -> None:
        self.calls.append(("pause", {}))

    def replies(self, on: bool) -> None:
        self.calls.append(("replies", {"on": on}))

    def takeover(self) -> None:
        self.calls.append(("takeover", {}))


@pytest.fixture
def engine() -> _ChildProcessEngine:
    result = object.__new__(_ChildProcessEngine)
    result.bots = [_Bot("Alice"), _Bot("Bob"), _Bot("Cleo")]  # pyright: ignore[reportAttributeAccessIssue]
    return result


def _calls(engine: _ChildProcessEngine) -> dict[str, list]:
    return {b.ign: b.calls for b in engine.bots}  # pyright: ignore[reportAttributeAccessIssue]


def test_replies_off_reaches_only_the_bots_it_names(
    engine: _ChildProcessEngine,
) -> None:
    engine._dispatch("REPLIES OFF Alice Bob")  # pyright: ignore[reportPrivateUsage]

    assert _calls(engine) == {
        "Alice": [("replies", {"on": False})],
        "Bob": [("replies", {"on": False})],
        "Cleo": [],
    }


def test_replies_on_for_all(engine: _ChildProcessEngine) -> None:
    engine._dispatch("REPLIES ON All")  # pyright: ignore[reportPrivateUsage]

    assert all(c == [("replies", {"on": True})] for c in _calls(engine).values())


def test_the_argument_is_never_taken_for_an_ign(engine: _ChildProcessEngine) -> None:
    engine._dispatch("REPLIES ON")  # pyright: ignore[reportPrivateUsage]

    assert all(c == [] for c in _calls(engine).values())


def test_pause_keeps_every_word_an_ign(engine: _ChildProcessEngine) -> None:
    engine._dispatch("PAUSE Bob")  # pyright: ignore[reportPrivateUsage]

    assert _calls(engine) == {"Alice": [], "Bob": [("pause", {})], "Cleo": []}


def test_takeover_reaches_the_bot_it_names(engine: _ChildProcessEngine) -> None:
    engine._dispatch("TAKEOVER Cleo")  # pyright: ignore[reportPrivateUsage]

    assert _calls(engine)["Cleo"] == [("takeover", {})]


def test_a_string_an_engine_sends_goes_to_discord_and_never_the_queue() -> None:
    """The mirror is a string down the Engine's pipe. It must not reach the
    TaskManager's queue, which only runs ActionRequests."""

    async def run() -> tuple[list[object], list[object]]:
        engine_end, listener_end = multiprocessing.Pipe()
        discord_main, discord_peripherals = multiprocessing.Pipe()
        queue: asyncio.Queue = asyncio.Queue()
        engine_end.send("[whisper] Bob: hi -> ya")
        engine_end.send(None)

        class _Process:
            name = "Engine(Alice)"

        task = Engine.listener(
            listener_end,  # pyright: ignore[reportArgumentType]
            queue,
            _Process(),  # pyright: ignore[reportArgumentType]
            discord_main,  # pyright: ignore[reportArgumentType]
        )
        await task
        discord = []
        while discord_peripherals.poll():
            discord.append(discord_peripherals.recv())
        queued = []
        while not queue.empty():
            queued.append(queue.get_nowait())
        return discord, queued

    discord, queued = asyncio.run(run())

    assert discord == ["[whisper] Bob: hi -> ya"]
    assert queued == [None]
