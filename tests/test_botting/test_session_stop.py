"""
How a Session ends, from `SessionManager`'s side: its `__exit__` releases every
Bot's keys in debug mode too, a `STOP` written during `launch` ends it
normally, an Engine that dies on an exception ends it in `error`, and
`__exit__` still writes `session.ended` and releases keys when a teardown step
raises, as they do after a console Ctrl+C kills the Manager process.

A real `SessionManager.__init__` starts a Manager process and configures
logging, so the instance is made with `__new__` and given the attributes
`__enter__`, `launch` and `__exit__` read. Engines are mocked: nothing here
spawns a process or touches a window.
"""

import asyncio
import json
import logging
import multiprocessing
import threading
from collections.abc import Callable, Iterator
from multiprocessing.connection import Connection
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pytest_mock import MockerFixture, MockType

from botting.core.async_task_manager import AsyncTaskManager
from botting.core.engine import Engine, EngineFailed, EngineFailure
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


# --- An Engine that dies on an exception ends the Session in error -----------

GRID_ERROR = "RuntimeError: Cannot generate grid for 'NoMapFile'"


def _dead_engine(*, fails: bool) -> Callable[..., SimpleNamespace]:
    """
    `Engine.start`, for a child process that exits at once: it writes to the
    real pipe what `_cycle_forever` sends on its way out, and spawns nothing.
    """

    def start(
        pipe: Connection, _metadata: object, bots: list[MockType], _barrier: object
    ) -> SimpleNamespace:
        name = f"Engine({', '.join(bot.ign for bot in bots)})"
        if fails:
            pipe.send(EngineFailure(engine=name, error=GRID_ERROR))
        pipe.send(None)
        return SimpleNamespace(
            name=name, join=lambda timeout=None: None, is_alive=lambda: False
        )

    return start


def test_engine_reports_its_failure_before_the_none_that_ends_it(
    mocker: MockerFixture,
) -> None:
    mocker.patch("botting.core.engine.install_loop_diagnostics")
    bot = _bot(mocker)
    bot.child_init.side_effect = RuntimeError("Cannot generate grid for 'NoMapFile'")
    engine = Engine.__new__(Engine)
    engine.pipe = mocker.Mock(closed=False)
    engine.metadata = {}  # pyright: ignore[reportAttributeAccessIssue]
    engine.bots = [bot]
    engine.bot_tasks = []
    engine.main_listener = None
    engine.barrier = mocker.Mock()

    with pytest.raises(RuntimeError):
        asyncio.run(engine._cycle_forever())  # pyright: ignore[reportPrivateUsage]

    assert engine.pipe.send.call_args_list == [
        mocker.call(EngineFailure(engine="Engine(Tester)", error=GRID_ERROR)),
        mocker.call(None),
    ]


def _listen(
    mocker: MockerFixture, *sent: object
) -> tuple[BaseException | None, asyncio.PriorityQueue]:
    """
    Run the real Listener over a real pipe its Engine has already written to.
    Returns what the Listener task raised, and the Task Manager's queue.
    """
    engine_side, listener_side = multiprocessing.Pipe()
    for message in sent:
        engine_side.send(message)
    engine = mocker.Mock()
    engine.name = "Engine(Tester)"
    queue: asyncio.PriorityQueue = asyncio.PriorityQueue()

    async def listen() -> BaseException | None:
        task = Engine.listener(listener_side, queue, engine, mocker.Mock())  # pyright: ignore[reportArgumentType]
        await asyncio.wait([task])
        return task.exception()

    return asyncio.run(listen()), queue


def test_the_listener_raises_its_engines_failure(mocker: MockerFixture) -> None:
    failure = EngineFailure(engine="Engine(Tester)", error=GRID_ERROR)

    raised, queue = _listen(mocker, failure, None)

    assert isinstance(raised, EngineFailed)
    assert str(raised) == f"Engine(Tester) raised {GRID_ERROR}"
    # The failure is no request: the queue gets only the None that ends it.
    assert queue.qsize() == 1
    assert queue.get_nowait() is None


def test_the_listener_of_an_engine_that_exits_normally_returns(
    mocker: MockerFixture,
) -> None:
    raised, _queue = _listen(mocker, None)

    assert raised is None


@pytest.mark.parametrize(
    ("fails", "cause", "error"),
    [
        pytest.param(
            True,
            "error",
            f"EngineFailed: Engine(Tester) raised {GRID_ERROR}",
            id="an engine that dies",
        ),
        pytest.param(False, "completed", None, id="an engine that exits normally"),
    ],
)
def test_session_ended_says_how_its_engine_ended(
    fails: bool,
    cause: str,
    error: str | None,
    mocker: MockerFixture,
    tmp_path: Path,
    sink: TelemetryHandler,
    released: MockType,
) -> None:
    """The live run of 2026-11-08 recorded a start-up crash as `completed`."""
    manager = _manager(mocker, tmp_path, sink, debug=True)
    mocker.patch(
        "botting.core.session_manager.Engine.start",
        side_effect=_dead_engine(fails=fails),
    )
    bot = _bot(mocker)

    async def scenario() -> None:
        with manager:
            await asyncio.wait_for(manager.launch([bot]), 2)

    if fails:
        with pytest.raises(EngineFailed):
            asyncio.run(scenario())
    else:
        asyncio.run(scenario())

    ended = _records(tmp_path)[-1]
    assert ended["event_type"] == "session.ended"
    assert ended["payload"] == {"cause": cause, "error": error}
    released.assert_called_with(HANDLE)


# --- __exit__ survives a teardown step that raises ---------------------------


def _break(mocker: MockerFixture, manager: SessionManager, step: str) -> None:
    """Make one teardown step raise, as a dead Manager process makes it."""
    target, attribute = {
        "log listener": (manager.log_receiver, "stop"),
        "peripherals": (manager.peripherals, "kill"),
        "engine": (manager.engines[0], "join"),
        "first bot": (manager.bots[0], "find_handle"),
    }[step]
    mocker.patch.object(target, attribute, side_effect=EOFError())


@pytest.mark.parametrize("step", ["log listener", "peripherals", "engine", "first bot"])
@pytest.mark.parametrize(
    ("exc", "cause"),
    [
        pytest.param(KeyboardInterrupt(), "interrupted", id="ctrl+c"),
        pytest.param(None, "completed", id="normal exit"),
    ],
)
def test_exit_survives_a_teardown_step_that_raises(
    step: str,
    exc: BaseException | None,
    cause: str,
    mocker: MockerFixture,
    tmp_path: Path,
    sink: TelemetryHandler,
    released: MockType,
) -> None:
    """
    After a console Ctrl+C, `log_receiver.stop()` raised `EOFError` through the
    dead Manager's queue and skipped everything after it, `session.ended` and
    the key release included.
    """
    manager = _manager(mocker, tmp_path, sink, debug=False)
    manager.discord_listener = mocker.Mock()
    manager.stop_file_task = mocker.Mock()
    hung, other = mocker.Mock(), mocker.Mock()
    hung.is_alive.return_value = True
    manager.engines = [hung, other]
    survivor = _bot(mocker)
    survivor.find_handle.return_value = HANDLE + 1
    manager.bots = [_bot(mocker), survivor]
    _break(mocker, manager, step)

    if exc is None:
        manager.__exit__(None, None, None)
    else:
        with pytest.raises(KeyboardInterrupt) as raised:
            manager.__exit__(type(exc), exc, None)
        # The exception that ended the Session, not the teardown's.
        assert raised.value is exc

    records = _records(tmp_path)
    assert records[-1]["event_type"] == "session.ended"
    assert records[-1]["payload"] == {"cause": cause, "error": None}
    assert sink not in logging.getLogger(PARENT_LOG).handlers
    assert sink._stream.closed  # pyright: ignore[reportPrivateUsage]
    hung.join.assert_called_once_with(timeout=2)
    other.join.assert_called_once_with(timeout=2)
    if step != "engine":
        hung.terminate.assert_called_once_with()
    released.assert_any_call(HANDLE + 1)
    if step != "first bot":
        released.assert_any_call(HANDLE)
