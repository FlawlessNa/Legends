"""
The launcher's contract: the spec, the stripped credentials, and the fake.

The herdr adapter has its own module. What is here is what every launcher shares,
so the fake and the adapter cannot drift on the rules the loop relies on.
"""

from __future__ import annotations

import dataclasses
import typing
from pathlib import Path

import pytest

from factory.launcher import (
    CREDENTIAL_VARIABLES,
    NO_CREDENTIALS_SENTINEL,
    Handle,
    Launcher,
    LauncherError,
    WorkerSpec,
    WorkerState,
    stripped_credentials,
    worker_spec,
)
from factory.launchers.fake import FakeLauncher

ROLES = ("designer", "spec-reviewer", "planner", "builder", "reviewer")


@pytest.fixture
def common_dir(tmp_path: Path) -> Path:
    path = tmp_path / "main" / ".git"
    path.mkdir(parents=True)
    return path


def make_spec(common_dir: Path, role: str = "builder", **over: object) -> WorkerSpec:
    kwargs: dict[str, typing.Any] = {
        "role": role,
        "stage": "build",
        "ticket": 7,
        "name": "t7-builder-1",
        "cwd": common_dir.parent,
        "model": "sonnet",
        "prompt": "do the thing",
        "common_dir": common_dir,
    }
    kwargs.update(over)
    return worker_spec(**kwargs)


def raw_spec(**over: object) -> WorkerSpec:
    kwargs: dict[str, typing.Any] = {
        "name": "t7-builder-1",
        "cwd": Path("."),
        "env": {},
        "model": "sonnet",
        "prompt": "p",
        "resume": None,
    }
    kwargs.update(over)
    return WorkerSpec(**kwargs)


# --- the shapes ---------------------------------------------------------------


def test_the_shapes_have_exactly_the_agreed_members() -> None:
    assert [f.name for f in dataclasses.fields(WorkerSpec)] == [
        "name",
        "cwd",
        "env",
        "model",
        "prompt",
        "resume",
    ]
    assert [f.name for f in dataclasses.fields(Handle)] == [
        "name",
        "pane_id",
        "role",
        "prompt_started",
    ]
    assert {s.value for s in WorkerState} == {
        "working",
        "finished",
        "blocked",
        "gone",
    }
    assert {s.name for s in WorkerState} == {s.value.upper() for s in WorkerState}
    assert typing.get_protocol_members(Launcher) == frozenset(
        {"start", "status", "session_id", "stop"}
    )


def test_the_specs_and_handles_are_frozen() -> None:
    spec = raw_spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.name = "other"  # type: ignore[misc]
    handle = Handle("a", "w1:p1", "builder", True)
    with pytest.raises(dataclasses.FrozenInstanceError):
        handle.name = "b"  # type: ignore[misc]


@pytest.mark.parametrize("name", ["a", "t7-builder-1", "a_b-c", "a" + "0" * 31])
def test_a_name_herdr_accepts_is_accepted(name: str) -> None:
    assert raw_spec(name=name).name == name


@pytest.mark.parametrize(
    "name", ["", "T7", "1abc", "-a", "_a", "a b", "a.b", "a" + "0" * 32, "é"]
)
def test_a_name_herdr_would_refuse_is_refused(name: str) -> None:
    with pytest.raises(ValueError, match="name"):
        raw_spec(name=name)


def test_resume_is_refused_unless_the_role_is_designer() -> None:
    assert raw_spec(env={"FACTORY_ROLE": "designer"}, resume="abc").resume == "abc"
    for env in ({}, {"FACTORY_ROLE": "builder"}):
        with pytest.raises(ValueError, match="resume"):
            raw_spec(env=env, resume="abc")


def test_the_spec_keeps_its_own_read_only_copy_of_env() -> None:
    env = {"A": "1"}
    spec = raw_spec(env=env)
    env["A"] = "changed"
    env["B"] = "2"
    assert dict(spec.env) == {"A": "1"}
    with pytest.raises(TypeError):
        spec.env["A"] = "x"  # type: ignore[index]


# --- stripped credentials -----------------------------------------------------


def test_stripped_credentials_are_exactly_these_eight(common_dir: Path) -> None:
    creds = stripped_credentials(common_dir)
    config_dir = creds["GH_CONFIG_DIR"]
    assert creds == {
        "GH_TOKEN": "factory-worker-has-no-credentials",
        "GH_CONFIG_DIR": config_dir,
        "GITHUB_TOKEN": "",
        "GIT_ASKPASS": "",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
    }
    assert NO_CREDENTIALS_SENTINEL == creds["GH_TOKEN"] != ""
    assert set(CREDENTIAL_VARIABLES) == set(creds)
    assert Path(config_dir).is_dir()
    assert Path(config_dir).parent.parent == common_dir


def test_stripped_credentials_is_repeatable_while_the_directory_is_empty(
    common_dir: Path,
) -> None:
    assert stripped_credentials(common_dir) == stripped_credentials(common_dir)


def test_stripped_credentials_raises_for_a_non_empty_directory(
    common_dir: Path,
) -> None:
    config_dir = Path(stripped_credentials(common_dir)["GH_CONFIG_DIR"])
    (config_dir / "hosts.yml").write_text("github.com: {}\n")
    with pytest.raises(LauncherError, match="GH_CONFIG_DIR"):
        stripped_credentials(common_dir)


# --- worker_spec --------------------------------------------------------------


@pytest.mark.parametrize("role", ROLES)
def test_worker_spec_carries_all_eight_credential_variables_for_every_role(
    common_dir: Path, role: str
) -> None:
    spec = make_spec(common_dir, role=role, stage="spec", ticket=42)
    expected = stripped_credentials(common_dir)
    assert len(expected) == 8
    for variable, value in expected.items():
        assert variable in spec.env, variable
        assert spec.env[variable] == value, variable
    assert spec.env["FACTORY_ROLE"] == role
    assert spec.env["FACTORY_STAGE"] == "spec"
    assert spec.env["FACTORY_TICKET"] == "42"


def test_worker_spec_passes_the_rest_through(common_dir: Path) -> None:
    spec = make_spec(common_dir, role="designer", resume="sess-1")
    assert (spec.name, spec.model, spec.prompt, spec.resume) == (
        "t7-builder-1",
        "sonnet",
        "do the thing",
        "sess-1",
    )
    with pytest.raises(ValueError, match="resume"):
        make_spec(common_dir, role="builder", resume="sess-1")


# --- the credential check, on the fake ----------------------------------------


@pytest.mark.parametrize("variable", sorted(CREDENTIAL_VARIABLES))
def test_start_refuses_a_spec_lacking_a_credential_variable(
    common_dir: Path, variable: str
) -> None:
    spec = make_spec(common_dir)
    env = {k: v for k, v in spec.env.items() if k != variable}
    launcher = FakeLauncher(common_dir)
    with pytest.raises(LauncherError, match=variable):
        launcher.start(dataclasses.replace(spec, env=env))
    assert launcher.started == []


@pytest.mark.parametrize("variable", sorted(CREDENTIAL_VARIABLES))
def test_start_refuses_a_spec_with_a_different_credential_value(
    common_dir: Path, variable: str
) -> None:
    spec = make_spec(common_dir)
    env = {**spec.env, variable: "something-else"}
    launcher = FakeLauncher(common_dir)
    with pytest.raises(LauncherError, match=variable):
        launcher.start(dataclasses.replace(spec, env=env))
    assert launcher.started == []


def test_start_refuses_a_spec_built_for_another_common_dir(
    common_dir: Path, tmp_path: Path
) -> None:
    other = tmp_path / "other" / ".git"
    other.mkdir(parents=True)
    spec = make_spec(other)
    with pytest.raises(LauncherError, match="GH_CONFIG_DIR"):
        FakeLauncher(common_dir).start(spec)


# --- FakeLauncher -------------------------------------------------------------


def test_the_fake_records_specs_in_order(common_dir: Path) -> None:
    launcher = FakeLauncher(common_dir)
    a = make_spec(common_dir, name="a")
    b = make_spec(common_dir, name="b", role="reviewer")
    handle_a = launcher.start(a)
    handle_b = launcher.start(b)
    assert launcher.started == [a, b]
    assert (handle_a.name, handle_a.role) == ("a", "builder")
    assert (handle_b.name, handle_b.role) == ("b", "reviewer")
    assert handle_a.prompt_started
    assert handle_a.pane_id != handle_b.pane_id


def test_the_fake_start_is_idempotent_by_name(common_dir: Path) -> None:
    launcher = FakeLauncher(common_dir)
    spec = make_spec(common_dir)
    first = launcher.start(spec)
    assert launcher.start(spec) == first
    assert launcher.started == [spec]


def test_the_fake_answers_status_from_a_script_one_call_at_a_time(
    common_dir: Path,
) -> None:
    launcher = FakeLauncher(
        common_dir,
        states={
            "a": [WorkerState.WORKING, WorkerState.BLOCKED, WorkerState.FINISHED],
            "b": [WorkerState.WORKING],
        },
    )
    a = launcher.start(make_spec(common_dir, name="a"))
    b = launcher.start(make_spec(common_dir, name="b"))
    assert [launcher.status(a) for _ in range(5)] == [
        WorkerState.WORKING,
        WorkerState.BLOCKED,
        WorkerState.FINISHED,
        WorkerState.FINISHED,
        WorkerState.FINISHED,
    ]
    assert launcher.status(b) is WorkerState.WORKING
    assert launcher.status(b) is WorkerState.WORKING


def test_the_fake_answers_session_id_from_a_script(common_dir: Path) -> None:
    launcher = FakeLauncher(common_dir, session_ids={"a": "sess-9"})
    a = launcher.start(make_spec(common_dir, name="a"))
    b = launcher.start(make_spec(common_dir, name="b"))
    assert launcher.session_id(a) == "sess-9"
    assert launcher.session_id(b) is None


def test_the_fake_stop_refuses_a_designer_and_closes_nothing(
    common_dir: Path,
) -> None:
    launcher = FakeLauncher(common_dir, states={"d": [WorkerState.WORKING]})
    handle = launcher.start(make_spec(common_dir, name="d", role="designer"))
    with pytest.raises(LauncherError, match="designer"):
        launcher.stop(handle)
    assert launcher.stopped == []
    assert launcher.status(handle) is WorkerState.WORKING


def test_after_the_fake_stops_a_worker_its_status_is_gone(common_dir: Path) -> None:
    launcher = FakeLauncher(common_dir, states={"a": [WorkerState.WORKING]})
    handle = launcher.start(make_spec(common_dir, name="a"))
    launcher.stop(handle)
    assert launcher.stopped == [handle]
    assert launcher.status(handle) is WorkerState.GONE


def test_a_relative_common_dir_still_gives_an_absolute_gh_config_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".git").mkdir()
    monkeypatch.chdir(tmp_path)
    relative = Path(".git")
    value = stripped_credentials(relative)["GH_CONFIG_DIR"]
    assert Path(value).is_absolute()
    assert Path(value).parent.parent == (tmp_path / ".git").resolve()
    FakeLauncher(relative).start(make_spec(relative))
