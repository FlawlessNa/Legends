"""
The factory loop's state outside the worktrees (#219).

Real temporary git repositories, because the state lives under the repository's
shared git directory and a linked worktree is the case that matters. The
concurrency test uses real processes: a thread cannot lose an update to a lock
that two processes share.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from factory import state
from factory.chain import front_matter
from factory.state import (
    Accepted,
    LogEntry,
    StateError,
    TicketState,
    dispatched,
    fresh,
    load,
    render_run_md,
    update,
    with_log,
)

from .test_park import add_ticket, git, make_repo

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def state_file(repo: Path, ticket: int) -> Path:
    return repo / ".git" / "factory" / str(ticket) / "state.json"


def entry(event: str = "dispatch", detail: str = "") -> LogEntry:
    return LogEntry(at="2026-10-23T10:00:00Z", event=event, detail=detail)


def full_state(ticket: int = 7) -> TicketState:
    return TicketState(
        ticket=ticket,
        stage="build-implementing",
        attempt=2,
        cycles={"review": 1, "spec-review": 2},
        worker="builder-1",
        turn_base="abc123",
        submitted="def456",
        accepted=Accepted(
            spec_blob="b1",
            base_sha="b2",
            accepted_by="nassim",
            accepted_at="2026-10-23T09:00:00Z",
        ),
        parked="needs a person",
        designer_session="sess-1",
        log=(entry("accepted"), entry("dispatch", "builder")),
    )


def put(repo: Path, new: TicketState) -> None:
    """Store `new` the only supported way: through `update`."""
    update(repo, new.ticket, lambda _old: new)


FIELDS = {
    "version",
    "ticket",
    "stage",
    "attempt",
    "cycles",
    "worker",
    "turn_base",
    "submitted",
    "accepted",
    "parked",
    "designer_session",
    "log",
}

# --- The shape of the state --------------------------------------------------


def test_a_fresh_state_has_exactly_the_documented_values() -> None:
    first = fresh(7)
    assert first.version == 1
    assert first.ticket == 7
    for name in (
        "stage",
        "worker",
        "turn_base",
        "submitted",
        "accepted",
        "parked",
        "designer_session",
    ):
        assert getattr(first, name) is None, name
    assert first.attempt == 0
    assert dict(first.cycles) == {}
    assert first.log == ()
    assert {field.name for field in dataclasses.fields(first)} == FIELDS


def test_load_gives_the_fresh_state_only_when_the_file_does_not_exist(
    repo: Path,
) -> None:
    assert load(repo, 7) == fresh(7)
    assert not state_file(repo, 7).exists()
    put(repo, full_state())
    assert load(repo, 7) == full_state()


def test_a_state_saved_and_loaded_again_is_equal(repo: Path) -> None:
    put(repo, full_state())
    again = load(repo, 7)
    assert again == full_state()
    assert again.accepted == full_state().accepted
    assert again.log == full_state().log


def test_the_state_lives_in_the_common_dir_of_a_linked_worktree(repo: Path) -> None:
    worktree = add_ticket(repo, 7)
    put(worktree, full_state())
    assert state_file(repo, 7).is_file()
    assert load(repo, 7) == load(worktree, 7)


def test_the_stored_file_holds_exactly_the_twelve_fields(repo: Path) -> None:
    put(repo, full_state())
    data = json.loads(state_file(repo, 7).read_text(encoding="utf-8"))
    assert set(data) == FIELDS
    assert set(data["accepted"]) == {
        "spec_blob",
        "base_sha",
        "accepted_by",
        "accepted_at",
    }


# --- A file that cannot be trusted -------------------------------------------


def _mutate(repo: Path, change: Callable[[dict[str, Any]], None]) -> None:
    put(repo, full_state())
    path = state_file(repo, 7)
    data = json.loads(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def _drop(key: str) -> Callable[[dict[str, Any]], None]:
    return lambda data: data.pop(key)


def _set(key: str, value: object) -> Callable[[dict[str, Any]], None]:
    def apply(data: dict[str, Any]) -> None:
        data[key] = value

    return apply


@pytest.mark.parametrize(
    ("field", "change"),
    [
        ("attempt", _drop("attempt")),
        ("log", _drop("log")),
        ("extra", _set("extra", 1)),
        ("attempt", _set("attempt", "2")),
        ("attempt", _set("attempt", True)),
        ("attempt", _set("attempt", -1)),
        ("stage", _set("stage", 3)),
        ("cycles", _set("cycles", [1])),
        ("cycles", _set("cycles", {"review": "1"})),
        ("accepted", _set("accepted", "yes")),
        ("accepted", _set("accepted", {"spec_blob": "x"})),
        ("log", _set("log", {"a": 1})),
        ("log", _set("log", [{"at": "t", "event": "e"}])),
        ("ticket", _set("ticket", 8)),
        ("version", _set("version", 2)),
    ],
)
def test_a_bad_file_raises_state_error_naming_the_file_and_the_field(
    repo: Path, field: str, change: Callable[[dict[str, Any]], None]
) -> None:
    _mutate(repo, change)
    with pytest.raises(StateError) as caught:
        load(repo, 7)
    assert str(state_file(repo, 7)) in str(caught.value)
    assert field in str(caught.value)


def test_malformed_json_raises_state_error_naming_the_file(repo: Path) -> None:
    put(repo, full_state())
    state_file(repo, 7).write_text("{not json", encoding="utf-8")
    with pytest.raises(StateError, match="state.json"):
        load(repo, 7)


def test_a_json_value_that_is_not_an_object_raises_state_error(repo: Path) -> None:
    put(repo, full_state())
    state_file(repo, 7).write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(StateError, match="state.json"):
        load(repo, 7)


def test_load_and_update_outside_a_repository_raise_state_error(
    tmp_path: Path,
) -> None:
    nowhere = tmp_path / "nowhere"
    nowhere.mkdir()
    with pytest.raises(StateError, match="repository"):
        load(nowhere, 7)
    with pytest.raises(StateError, match="repository"):
        update(nowhere, 7, lambda old: old)
    assert not (nowhere / "factory").exists()


# --- Writes ------------------------------------------------------------------


class Killed(BaseException):
    """Stands in for a process killed between the temp write and the replace."""


def test_an_interrupted_write_leaves_the_previous_state_readable(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old = full_state()
    put(repo, old)
    new = dataclasses.replace(old, attempt=3)
    seen: dict[str, object] = {}

    def fake_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        source, target = Path(src), Path(dst)
        seen["exists"] = source.is_file()
        seen["same_dir"] = source.parent == target.parent
        seen["is_new"] = json.loads(source.read_text(encoding="utf-8"))["attempt"] == 3
        seen["target"] = target.name
        raise Killed

    monkeypatch.setattr(state.os, "replace", fake_replace)
    with pytest.raises(Killed):
        update(repo, 7, lambda _old: new)
    assert seen == {
        "exists": True,
        "same_dir": True,
        "is_new": True,
        "target": "state.json",
    }
    monkeypatch.undo()
    assert load(repo, 7) == old


def test_a_killed_update_does_not_leave_the_lock_held(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(repo, full_state())

    def fake_replace(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        raise Killed

    monkeypatch.setattr(state.os, "replace", fake_replace)
    with pytest.raises(Killed):
        update(repo, 7, lambda old: dataclasses.replace(old, attempt=9))
    monkeypatch.undo()
    monkeypatch.setattr(state, "LOCK_TIMEOUT", 0.5)
    assert update(repo, 7, lambda old: old) == full_state()


def test_a_stale_temp_file_never_shadows_state_json(repo: Path) -> None:
    ghost = dataclasses.replace(full_state(), attempt=9, worker="ghost")
    put(repo, ghost)
    stale_text = state_file(repo, 7).read_text(encoding="utf-8")
    put(repo, full_state())
    (state_file(repo, 7).parent / "state.json.tmp-424242").write_text(
        stale_text, encoding="utf-8"
    )
    assert load(repo, 7) == full_state()
    assert update(repo, 7, lambda old: old) == full_state()


def test_a_permission_error_is_retried_then_raised(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(repo, full_state())
    monkeypatch.setattr(state, "RETRY_DELAY", 0.0)
    calls: list[int] = []

    def refuse(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        calls.append(1)
        raise PermissionError("a reader holds it")

    monkeypatch.setattr(state.os, "replace", refuse)
    with pytest.raises(StateError, match="state.json"):
        update(repo, 7, lambda old: dataclasses.replace(old, attempt=9))
    assert len(calls) == state.RETRIES
    monkeypatch.undo()
    assert load(repo, 7) == full_state()


def test_a_transient_permission_error_on_replace_is_survived(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(repo, full_state())
    monkeypatch.setattr(state, "RETRY_DELAY", 0.0)
    real = os.replace
    left = [3]

    def flaky(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if left[0]:
            left[0] -= 1
            raise PermissionError("busy")
        real(src, dst)

    monkeypatch.setattr(state.os, "replace", flaky)
    update(repo, 7, lambda old: dataclasses.replace(old, attempt=9))
    monkeypatch.undo()
    assert load(repo, 7).attempt == 9


def _deny_reads(monkeypatch: pytest.MonkeyPatch, times: int) -> list[int]:
    real = Path.read_text
    left = [times]
    calls: list[int] = []

    def read_text(self: Path, encoding: str | None = None) -> str:
        if self.name == "state.json" and left[0]:
            left[0] -= 1
            calls.append(1)
            raise PermissionError("a writer holds it")
        return real(self, encoding=encoding)

    monkeypatch.setattr(Path, "read_text", read_text)
    return calls


def test_load_retries_a_permission_error_and_then_reads_the_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(repo, full_state())
    monkeypatch.setattr(state, "RETRY_DELAY", 0.0)
    calls = _deny_reads(monkeypatch, 3)
    assert load(repo, 7) == full_state()
    assert len(calls) == 3


def test_load_never_reads_a_permission_error_as_a_missing_file(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(repo, full_state())
    monkeypatch.setattr(state, "RETRY_DELAY", 0.0)
    _deny_reads(monkeypatch, 10_000)
    with pytest.raises(StateError, match="state.json"):
        load(repo, 7)


# --- The lock ----------------------------------------------------------------

_BUMP = """
import dataclasses, sys, time
from pathlib import Path
from factory import state

repo, go = Path(sys.argv[1]), float(sys.argv[2])
time.sleep(max(0.0, go - time.time()))

def change(old):
    seen = old.attempt
    time.sleep(0.3)
    return dataclasses.replace(old, attempt=seen + 1)

state.update(repo, 7, change)
"""


def test_two_processes_updating_at_once_lose_neither_update(repo: Path) -> None:
    """
    Each process reads `attempt`, sleeps inside the change, then writes it plus
    one. Both start at the same instant, so without the lock both read 0 and
    the file ends at 1, every time.
    """
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    go = time.time() + 2.0
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", _BUMP, str(repo), str(go)],
            cwd=REPO_ROOT,
            env=env,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(2)
    ]
    errors = [proc.communicate(timeout=60)[1] for proc in procs]
    assert [proc.returncode for proc in procs] == [0, 0], errors
    assert load(repo, 7).attempt == 2


def test_the_lock_wait_is_bounded_then_state_error(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(repo, full_state())
    monkeypatch.setattr(state, "LOCK_TIMEOUT", 0.3)
    directory = state_file(repo, 7).parent
    started = time.monotonic()
    with state.locked(directory), pytest.raises(StateError, match="state.lock"):
        update(repo, 7, lambda old: old)
    assert time.monotonic() - started < 5
    assert update(repo, 7, lambda old: old) == full_state()


# --- Immutability, and a log that only grows ---------------------------------


def test_cycles_and_log_are_read_only_once_constructed() -> None:
    source = {"review": 1}
    made = TicketState(ticket=7, cycles=source, log=(entry(),))
    source["review"] = 5
    assert made.cycles["review"] == 1
    assert isinstance(made.log, tuple)
    with pytest.raises(TypeError):
        made.cycles["review"] = 2  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        made.attempt = 3  # type: ignore[misc]


def test_with_log_appends_and_leaves_the_original_alone() -> None:
    first = with_log(fresh(7), entry("a"))
    second = with_log(first, entry("b"))
    assert [e.event for e in first.log] == ["a"]
    assert [e.event for e in second.log] == ["a", "b"]


def test_update_refuses_a_change_that_shortens_or_rewrites_the_log(
    repo: Path,
) -> None:
    put(repo, full_state())
    with pytest.raises(StateError, match="log"):
        update(repo, 7, lambda old: dataclasses.replace(old, log=old.log[:1]))
    with pytest.raises(StateError, match="log"):
        update(repo, 7, lambda old: dataclasses.replace(old, log=(entry("x"),)))
    assert load(repo, 7) == full_state()
    update(repo, 7, lambda old: with_log(old, entry("more")))
    assert len(load(repo, 7).log) == 3


def test_update_refuses_a_change_that_renames_the_ticket(repo: Path) -> None:
    with pytest.raises(StateError, match="ticket"):
        update(repo, 7, lambda old: dataclasses.replace(old, ticket=8))
    assert not state_file(repo, 7).exists()


# --- dispatched --------------------------------------------------------------


def test_dispatched_counts_a_stage_from_one_and_resets_on_a_new_stage() -> None:
    one = dispatched(fresh(7), "build-implementing")
    assert (one.stage, one.attempt) == ("build-implementing", 1)
    two = dispatched(one, "build-implementing")
    assert two.attempt == 2
    other = dispatched(two, "review")
    assert (other.stage, other.attempt) == ("review", 1)
    assert two.attempt == 2


# --- render_run_md -----------------------------------------------------------


def test_render_is_identical_whatever_order_cycles_was_built_in() -> None:
    forward = dataclasses.replace(full_state(), cycles={"a": 1, "b": 2, "c": 3})
    backward = dataclasses.replace(full_state(), cycles={"c": 3, "b": 2, "a": 1})
    assert forward == backward
    assert render_run_md(forward) == render_run_md(backward)


def test_render_has_the_front_matter_and_a_table_of_the_log_in_order(
    tmp_path: Path,
) -> None:
    text = render_run_md(full_state())
    path = tmp_path / "run.md"
    path.write_text(text, encoding="utf-8")
    front = front_matter(path)
    assert front["ticket"] == "7"
    assert front["stage"] == "build-implementing"
    assert front["attempt"] == "2"
    assert front["cycles.review"] == "1"
    #: The reader skips a hyphenated key, so the raw block is checked as well.
    block = text.split("cycles:\n", 1)[1].split("---", 1)[0]
    assert block.splitlines() == ["  review: 1", "  spec-review: 2"]
    body = text.split("\n---\n", 1)[1]
    rows = [line for line in body.splitlines() if line.startswith("| ")]
    assert len(rows) == 4
    assert "accepted" in rows[2]
    assert "dispatch" in rows[3]
    assert "builder" in rows[3]


def test_render_escapes_a_pipe_or_newline_in_a_log_cell() -> None:
    odd = with_log(fresh(7), entry("note", "a | b\nc"))
    rows = [ln for ln in render_run_md(odd).splitlines() if ln.startswith("| ")]
    assert len(rows) == 3
    assert "a \\| b c" in rows[2]


def test_render_of_a_fresh_state_is_valid() -> None:
    text = render_run_md(fresh(7))
    assert text.startswith("---\n")
    assert "ticket: 7" in text


# --- Nothing leaks into a worktree -------------------------------------------


def _statuses(roots: list[Path]) -> dict[Path, str]:
    return {root: git(root, "status", "--porcelain", "--ignored") for root in roots}


def test_state_never_changes_git_status_in_any_worktree(repo: Path) -> None:
    roots = [repo, add_ticket(repo, 7), add_ticket(repo, 8)]
    before = _statuses(roots)
    put(roots[1], full_state())
    update(roots[2], 8, lambda old: dispatched(old, "plan"))
    load(roots[1], 7)
    render_run_md(load(roots[2], 8))
    assert _statuses(roots) == before
