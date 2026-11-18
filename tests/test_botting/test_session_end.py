"""
What lets a Session end cleanly, and run without Discord.

* The Session publishes its directory in the metadata the Engines read, which is
  how a finished calibration schedule finds the stop file to write.
* A child process ends with its parent, however the parent ends, so a launcher
  killed from outside leaves no Engine behind.
* With Discord off the Peripherals process builds no Discord client, and drops
  every message meant for it.
"""

import asyncio
import multiprocessing
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from botting.core import peripherals_process
from botting.core.peripherals_process import PeripheralsProcess, drain_pipe
from botting.core.session_manager import SessionManager
from paths import ROOT


def test_the_session_publishes_its_directory_to_the_engines(
    mocker: MockerFixture, tmp_path: Path
) -> None:
    manager = mocker.patch("botting.core.session_manager.multiprocessing.Manager")
    manager.return_value.dict.side_effect = dict
    mocker.patch("botting.core.session_manager.new_session_dir", return_value=tmp_path)
    mocker.patch("botting.core.session_manager.logging.config.dictConfig")
    mocker.patch("botting.core.session_manager.full_config")
    mocker.patch("botting.core.session_manager.TelemetryHandler")
    mocker.patch("botting.core.session_manager.logging.handlers.QueueListener")
    mocker.patch("botting.core.session_manager.logging.getLogger")
    mocker.patch("botting.core.session_manager.PeripheralsProcess")

    session = SessionManager(mocker.Mock())

    assert session.metadata["session_dir"] == str(tmp_path)
    # Not a proxy request: `_monitor_proxy` would otherwise try to serve it.
    assert "session_dir" in session.metadata["ignored_keys"]


def test_a_discord_off_peripheral_drops_what_is_meant_for_discord() -> None:
    main_end, child_end = multiprocessing.Pipe()
    for message in ("an alert", "another"):
        main_end.send(message)
    main_end.send(None)

    asyncio.run(asyncio.wait_for(drain_pipe(child_end), timeout=10))  # pyright: ignore[reportArgumentType] - Windows types Pipe() ends as PipeConnection

    assert not child_end.poll()


def test_a_discord_off_peripheral_builds_no_discord_client(
    mocker: MockerFixture,
) -> None:
    def refused(*_args: object) -> None:
        raise AssertionError("a Discord client was built")

    mocker.patch.object(peripherals_process, "DiscordIO", refused)
    mocker.patch.object(peripherals_process, "install_loop_diagnostics")

    async def never_ends() -> None:
        await asyncio.Event().wait()

    mocker.patch.object(
        peripherals_process,
        "Recorder",
        return_value=SimpleNamespace(start=never_ends),
    )
    peripherals = PeripheralsProcess(mocker.Mock(), mocker.Mock(), discord=False)
    peripherals.pipe_main_proc.send(None)  # the Session is stopping

    asyncio.run(asyncio.wait_for(peripherals._launch_tasks(), timeout=10))


_PARENT = textwrap.dedent(
    """
    import multiprocessing, time
    from botting.utilities import exit_with_parent


    def child():
        exit_with_parent()
        while True:
            time.sleep(0.05)


    if __name__ == "__main__":
        process = multiprocessing.Process(target=child)
        process.start()
        print(process.pid, flush=True)
        time.sleep(600)
    """
)


def _alive(pid: int) -> bool:
    out = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return str(pid) in out


@pytest.mark.skipif(sys.platform != "win32", reason="uses the Windows process list")
def test_a_child_ends_when_its_parent_is_killed(tmp_path: Path) -> None:
    script = tmp_path / "parent.py"
    script.write_text(_PARENT, encoding="utf-8")
    parent = subprocess.Popen(
        [sys.executable, str(script)],
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT)},
        stdout=subprocess.PIPE,
        text=True,
    )
    assert parent.stdout is not None
    child_pid = int(parent.stdout.readline())
    try:
        assert _alive(child_pid)
        parent.kill()
        parent.wait(timeout=30)
        deadline = time.monotonic() + 30
        while _alive(child_pid) and time.monotonic() < deadline:
            time.sleep(0.2)
        assert not _alive(child_pid)
    finally:
        parent.kill()
        subprocess.run(
            ["taskkill", "/F", "/PID", str(child_pid)],
            capture_output=True,
            check=False,
        )
