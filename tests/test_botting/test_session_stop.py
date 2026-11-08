"""
How a Session ends through the stop file, from `SessionManager`'s side: its
`__exit__` releases every Bot's keys in debug mode too, and a `STOP` written
during `launch` ends it normally, with `session.ended` the last record.

A real `SessionManager.__init__` starts a Manager process and configures
logging, so the instance is made with `__new__` and given the attributes
`__enter__`, `launch` and `__exit__` read. Engines are mocked: nothing here
spawns a process or touches a window.
"""

import asyncio
import json
import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytest_mock import MockerFixture, MockType

from botting.core.async_task_manager import AsyncTaskManager
from botting.core.session_manager import SessionManager
from botting.logging_config import PARENT_LOG
from botting.stop_file import request_stop
from botting.telemetry import TELEMETRY_FILENAME, TelemetryHandler

HANDLE = 4242


async def _forever(*_args: object, **_kwargs: object) -> None:
    await asyncio.Event().wait()


@pytest.fixture
def released(mocker: MockerFixture) -> MockType:
    """`release_all` as `SessionManager` calls it; no key is sent."""
    mocker.patch("botting.core.session_manager.HeldKeysLedger")
    mocker.patch("botting.core.session_manager.install_loop_diagnostics")
    return mocker.patch("botting.core.session_manager.release_all")


@pytest.fixture
def sink(tmp_path: Path) -> Iterator[TelemetryHandler]:
    """The Session's real JSONL sink, on the `botting` logger as in a Session."""
    handler = TelemetryHandler(tmp_path / TELEMETRY_FILENAME)
    logging.getLogger(PARENT_LOG).addHandler(handler)
    yield handler
    logging.getLogger(PARENT_LOG).removeHandler(handler)
    handler.close()


def _bot(mocker: MockerFixture) -> MockType:
    bot = mocker.Mock()
    bot.ign = "Tester"
    bot.find_handle.return_value = HANDLE
    bot._decision_makers.return_value = []
    return bot


def _manager(
    mocker: MockerFixture, session_dir: Path, sink: TelemetryHandler, *, debug: bool
) -> SessionManager:
    """A SessionManager with every attribute its lifecycle reads, and no process."""
    manager = SessionManager.__new__(SessionManager)
    manager._debug = debug
    manager.session_dir = session_dir
    manager.telemetry_handler = sink
    manager.log_receiver = mocker.Mock()
    manager.process_manager = mocker.Mock()
    manager.metadata = {"proxy_request": threading.Condition()}  # pyright: ignore[reportAttributeAccessIssue]
    manager.peripherals = mocker.Mock()
    manager.peripherals.peripherals_listener = mocker.AsyncMock(side_effect=_forever)
    manager.peripherals.engine_pipes = []
    manager.task_manager = AsyncTaskManager(mocker.Mock())
    manager.engines = []
    manager.listeners = []
    manager.discord_listener = None
    manager.proxy_listener = None
    manager.management_task = None
    manager.stop_file_task = None
    manager.main_bot = None
    manager.bots = []
    manager.stop_reason = None
    manager.barrier = None
    return manager


def _records(session_dir: Path) -> list[dict[str, Any]]:
    lines = (session_dir / TELEMETRY_FILENAME).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


# --- __exit__ releases keys in debug mode too --------------------------------


@pytest.mark.parametrize("debug", [True, False], ids=["debug", "not debug"])
def test_exit_releases_every_bots_keys(
    debug: bool,
    mocker: MockerFixture,
    tmp_path: Path,
    sink: TelemetryHandler,
    released: MockType,
) -> None:
    """Debug mode used to skip it, so a stopped `bot_tester` Session could leave a key held."""
    manager = _manager(mocker, tmp_path, sink, debug=debug)
    manager.bots = [_bot(mocker), _bot(mocker)]
    manager.discord_listener = mocker.Mock()
    manager.stop_file_task = mocker.Mock()

    manager.__exit__(None, None, None)

    assert released.call_args_list == [mocker.call(HANDLE), mocker.call(HANDLE)]


def test_exit_cancels_the_stop_file_watch_before_session_ended(
    mocker: MockerFixture, tmp_path: Path, sink: TelemetryHandler, released: MockType
) -> None:
    order: list[str] = []
    manager = _manager(mocker, tmp_path, sink, debug=False)
    manager.discord_listener = mocker.Mock()
    watch = mocker.Mock()
    watch.cancel.side_effect = lambda *_: order.append("cancel")
    manager.stop_file_task = watch
    mocker.patch(
        "botting.core.session_manager.emit_event",
        side_effect=lambda *_a, **_k: order.append("session.ended"),
    )

    manager.__exit__(None, None, None)

    assert order == ["cancel", "session.ended"]


# --- A stop file ends launch normally ----------------------------------------


def _launch_and_stop(
    mocker: MockerFixture, manager: SessionManager, write_stop: bool
) -> float:
    """
    Run `__enter__`, `launch` with one mocked Engine and `__exit__`, writing
    the stop file once `launch` is under way. Returns how long `launch` took.
    Fails if it takes more than 2 s.
    """
    mocker.patch("botting.core.session_manager.Engine.start")
    mocker.patch(
        "botting.core.session_manager.Engine.listener",
        side_effect=lambda *_a: asyncio.create_task(_forever()),
    )
    bot = _bot(mocker)

    async def scenario() -> float:
        loop = asyncio.get_running_loop()
        with manager:
            launching = asyncio.create_task(manager.launch([bot]))
            await asyncio.sleep(0.05)
            started = loop.time()
            if write_stop:
                request_stop(manager.session_dir, "tests done")
            await asyncio.wait_for(launching, 2)
            return loop.time() - started

    return asyncio.run(scenario())


def test_a_stop_file_ends_launch_normally_within_2_s(
    mocker: MockerFixture, tmp_path: Path, sink: TelemetryHandler, released: MockType
) -> None:
    manager = _manager(mocker, tmp_path, sink, debug=False)

    elapsed = _launch_and_stop(mocker, manager, write_stop=True)

    assert elapsed < 2
    assert manager.stop_reason == "tests done"
    released.assert_called_with(HANDLE)


def test_a_stopped_session_records_why_and_ends_on_session_ended(
    mocker: MockerFixture, tmp_path: Path, sink: TelemetryHandler, released: MockType
) -> None:
    """
    Read after the event loop has shut down, so every task it cancelled on the
    way out has run: none of them wrote after `session.ended`.
    """
    manager = _manager(mocker, tmp_path, sink, debug=True)

    _launch_and_stop(mocker, manager, write_stop=True)

    records = _records(tmp_path)
    types = [r["event_type"] for r in records]
    assert types.count("session.stop_requested") == 1
    stop = records[types.index("session.stop_requested")]
    assert stop["payload"] == {"reason": "tests done"}
    assert records[-1]["event_type"] == "session.ended"
    assert records[-1]["payload"] == {"cause": "stop_file", "error": None}
