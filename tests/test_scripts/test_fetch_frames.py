"""`fetch_frames.py` fetches a tag with `gh`, and says one thing when `gh` isn't logged in."""

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
from pytest_mock import MockerFixture

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fetch_frames.py"


@pytest.fixture
def script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fetch_frames", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def completed(code: int, stdout: str = "", stderr: str = "") -> object:
    return subprocess.CompletedProcess([], code, stdout, stderr)


def test_not_logged_in_fails_naming_gh_auth_login(
    script: ModuleType, mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(script.shutil, "which", return_value="gh")
    run = mocker.patch.object(script.subprocess, "run", return_value=completed(1))

    with pytest.raises(SystemExit) as exit_info:
        script.fetch("v1", "me/legends-frames", tmp_path)

    message = str(exit_info.value)
    assert "gh auth login" in message
    assert "\n" not in message
    assert run.call_count == 1  # only `gh auth status`; nothing was downloaded


def test_downloads_the_tag_into_its_folder(
    script: ModuleType, mocker: MockerFixture, tmp_path: Path
) -> None:
    mocker.patch.object(script.shutil, "which", return_value="gh")
    run = mocker.patch.object(script.subprocess, "run", return_value=completed(0))

    target = script.fetch("v1", "me/legends-frames", tmp_path)

    assert target == tmp_path / "v1"
    command = run.call_args_list[-1].args[0]
    assert command[:4] == ["gh", "release", "download", "v1"]
    assert command[command.index("--repo") + 1] == "me/legends-frames"
    assert command[command.index("--dir") + 1] == str(tmp_path / "v1")


def test_no_tag_uses_current(script: ModuleType, mocker: MockerFixture) -> None:
    fetch = mocker.patch.object(script, "fetch", return_value=Path("."))
    mocker.patch.object(script, "current_tag", return_value="v7")

    script.main(["--repo", "me/frames"])

    fetch.assert_called_once_with("v7", "me/frames")


def test_default_repo_is_the_origin_owners(
    script: ModuleType, mocker: MockerFixture
) -> None:
    for url in (
        "https://github.com/Owner/Legends.git\n",
        "git@github.com:Owner/Legends.git\n",
    ):
        mocker.patch.object(
            script.subprocess, "run", return_value=completed(0, stdout=url)
        )
        assert script.default_repo() == "Owner/legends-frames"
