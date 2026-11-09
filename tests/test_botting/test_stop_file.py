"""
The stop file: `watch_stop_file` on its own, with a temporary Session directory
and a plain queue standing in for the Task Manager's, and `request_stop`, the
writer `python -m botting.session stop` uses.

No `SessionManager` is built here; `test_session_stop.py` covers its side.
"""

import asyncio
from pathlib import Path

import pytest
from pytest_mock import MockerFixture, MockType

from botting.stop_file import (
    NO_REASON,
    STOP_FILENAME,
    request_stop,
    watch_stop_file,
)
from botting.telemetry_events import SESSION_STOP_REQUESTED

#: Seconds between looks, for the tests that don't pin the real interval.
FAST = 0.01


@pytest.fixture
def emitted(mocker: MockerFixture) -> MockType:
    return mocker.patch("botting.stop_file.emit_event")


async def _watch_until_stopped(
    session_dir: Path,
    reasons: list[str],
    *,
    write: str | None,
    timeout: float,
    interval: float = FAST,
) -> object:
    """
    Run the watch, write the stop file once it runs (unless `write` is None),
    and return what reaches the queue within `timeout`. The watch is cancelled
    afterwards either way.
    """
    queue: asyncio.Queue[object] = asyncio.Queue()
    task = asyncio.create_task(
        watch_stop_file(session_dir, queue, reasons.append, interval=interval)
    )
    try:
        await asyncio.sleep(0)
        if write is not None:
            request_stop(session_dir, write)
        return await asyncio.wait_for(queue.get(), timeout)
    finally:
        task.cancel()


def test_a_stop_file_puts_none_on_the_queue_within_3_s(
    tmp_path: Path, emitted: MockType
) -> None:
    """At the real interval: one look a second is well inside 3 s."""
    reasons: list[str] = []

    async def scenario() -> object:
        queue: asyncio.Queue[object] = asyncio.Queue()
        task = asyncio.create_task(watch_stop_file(tmp_path, queue, reasons.append))
        try:
            await asyncio.sleep(0)
            request_stop(tmp_path, "tests done")
            return await asyncio.wait_for(queue.get(), 3)
        finally:
            task.cancel()

    assert asyncio.run(scenario()) is None
    emitted.assert_called_once_with(
        None,
        SESSION_STOP_REQUESTED,
        {"reason": "tests done"},
        logger_name="botting.stop_file",
    )
    assert reasons == ["tests done"]


def test_the_reason_is_stored_before_none_is_queued(
    tmp_path: Path, emitted: MockType
) -> None:
    """`launch` may return as soon as `None` is read; `session.ended` needs the reason by then."""
    queued_when_stored: list[bool] = []

    async def scenario() -> None:
        queue: asyncio.Queue[object] = asyncio.Queue()

        def store(_reason: str) -> None:
            queued_when_stored.append(not queue.empty())

        task = asyncio.create_task(
            watch_stop_file(tmp_path, queue, store, interval=FAST)
        )
        request_stop(tmp_path, "tests done")
        await asyncio.wait_for(queue.get(), 1)
        task.cancel()

    asyncio.run(scenario())

    assert queued_when_stored == [False]


def test_the_stop_is_logged_as_a_warning_with_its_reason(
    tmp_path: Path, emitted: MockType, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="botting.stop_file"):
        asyncio.run(_watch_until_stopped(tmp_path, [], write="tests done", timeout=1))

    assert [r.levelname for r in caplog.records] == ["WARNING"]
    assert "tests done" in caplog.records[0].getMessage()


def test_an_empty_stop_file_still_stops_the_session(
    tmp_path: Path, emitted: MockType
) -> None:
    reasons: list[str] = []

    assert (
        asyncio.run(_watch_until_stopped(tmp_path, reasons, write="", timeout=1))
        is None
    )
    assert reasons == [NO_REASON]


def test_the_reason_is_read_without_surrounding_whitespace(
    tmp_path: Path, emitted: MockType
) -> None:
    reasons: list[str] = []

    asyncio.run(_watch_until_stopped(tmp_path, reasons, write="  done\r\n", timeout=1))

    assert reasons == ["done"]


def test_without_a_stop_file_nothing_happens(tmp_path: Path, emitted: MockType) -> None:
    reasons: list[str] = []

    with pytest.raises(TimeoutError):
        asyncio.run(_watch_until_stopped(tmp_path, reasons, write=None, timeout=0.2))

    emitted.assert_not_called()
    assert reasons == []


def test_a_file_that_cannot_be_read_yet_is_tried_again(
    tmp_path: Path, emitted: MockType, mocker: MockerFixture
) -> None:
    """A writer holding the file open on Windows: retried at the next look, never raised."""
    real = Path.read_bytes
    calls: list[Path] = []

    def locked_once(self: Path) -> bytes:
        calls.append(self)
        if len(calls) == 1 and self.exists():
            raise PermissionError("in use")
        return real(self)

    mocker.patch.object(Path, "read_bytes", locked_once)
    request_stop(tmp_path, "tests done")
    reasons: list[str] = []

    assert (
        asyncio.run(_watch_until_stopped(tmp_path, reasons, write=None, timeout=1))
        is None
    )
    assert reasons == ["tests done"]
    assert len(calls) >= 2


def test_after_the_request_the_watch_waits_to_be_cancelled(
    tmp_path: Path, emitted: MockType
) -> None:
    """
    `launch` ends on its first finished task, and that should be the Task
    Manager reading `None`, not the watch: it would get the Task Manager
    cancelled mid-request.
    """

    async def scenario() -> bool:
        queue: asyncio.Queue[object] = asyncio.Queue()
        task = asyncio.create_task(
            watch_stop_file(tmp_path, queue, print, interval=FAST)
        )
        request_stop(tmp_path, "tests done")
        await asyncio.wait_for(queue.get(), 1)
        await asyncio.sleep(10 * FAST)
        done = task.done()
        task.cancel()
        return done

    assert asyncio.run(scenario()) is False


def test_a_cancelled_watch_emits_nothing_whatever_appears(
    tmp_path: Path, emitted: MockType
) -> None:
    """`__exit__` cancels the watch before `session.ended`, which must stay last."""
    reasons: list[str] = []

    async def scenario() -> None:
        queue: asyncio.Queue[object] = asyncio.Queue()
        task = asyncio.create_task(
            watch_stop_file(tmp_path, queue, reasons.append, interval=FAST)
        )
        await asyncio.sleep(0)
        task.cancel()
        request_stop(tmp_path, "too late")
        await asyncio.sleep(10 * FAST)
        assert queue.empty()

    asyncio.run(scenario())

    emitted.assert_not_called()
    assert reasons == []


def test_request_stop_writes_the_reason_whole(tmp_path: Path) -> None:
    path = request_stop(tmp_path, "tests done")

    assert path == tmp_path / STOP_FILENAME
    assert path.read_text(encoding="utf-8") == "tests done"
    assert [p.name for p in tmp_path.iterdir()] == [STOP_FILENAME]
