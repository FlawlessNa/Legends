"""
The herdr adapter, driven only by herdr replies stored under fixtures/herdr/.

No test here reaches the real `herdr` binary: an autouse guard replaces the
module's default runner with one that fails the test. Every other path goes
through `ScriptedHerdr`, which answers a command from a stored file and records
the argument list it was given.

Provenance. herdr 0.9.5 is the version every file is tied to. A file is either
CAPTURED (taken from the running herdr or from a real Claude Code startup in it,
trimmed to the fields the adapter reads) or CONSTRUCTED (built by hand from that
version's bundled API schema, because creating a pane is out of bounds for a
test). `PROVENANCE` says which, and `test_every_stored_reply_says_where_it_came_from`
fails when a file is missing from it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
import typing
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

from factory.launcher import (
    Handle,
    LauncherError,
    WorkerSpec,
    WorkerState,
    worker_spec,
)
from factory.launchers import herdr as herdr_module
from factory.launchers.herdr import (
    CommandResult,
    HerdrLauncher,
    Timeouts,
    is_linked_worktree,
    read_process_table,
    trust_dialog_matches,
)

HERDR_VERSION = "0.9.5"
FIXTURES = Path(__file__).parent / "fixtures" / "herdr"
REPO_ROOT = Path(__file__).resolve().parents[2]

CAPTURED = "captured"
CONSTRUCTED = "constructed"

PROVENANCE: dict[str, str] = {
    # Taken from herdr 0.9.5 on 2026-10-22 with read-only commands.
    "agent_not_found.json": CAPTURED,
    "pane_not_found.json": CAPTURED,
    # A real Claude Code startup in a fresh folder, read in herdr 0.9.5 on
    # 2026-10-22 with `agent read --source recent-unwrapped`.
    "trust-dialog-live.txt": CAPTURED,
    # Variations of that screen, edited by hand.
    "trust-dialog-yes-first.txt": CONSTRUCTED,
    "trust-dialog-numbered.txt": CONSTRUCTED,
    "trust-dialog-numbered-gap.txt": CONSTRUCTED,
    "trust-dialog-cursor-on-yes.txt": CONSTRUCTED,
    "trust-dialog-between.txt": CONSTRUCTED,
    "trust-dialog-no-question.txt": CONSTRUCTED,
    "blocked-mcp-approval.txt": CONSTRUCTED,
    # Replies from mutating commands, and from reads that need a live agent.
    "agent_get_working.json": CONSTRUCTED,
    "agent_get_idle.json": CONSTRUCTED,
    "agent_get_done.json": CONSTRUCTED,
    "agent_get_blocked.json": CONSTRUCTED,
    "agent_get_unknown.json": CONSTRUCTED,
    "agent_get_sleeping.json": CONSTRUCTED,
    "agent_get_idle_other_pane.json": CONSTRUCTED,
    "error_other.json": CONSTRUCTED,
    "not_json.txt": CONSTRUCTED,
    "agent_not_ready.json": CONSTRUCTED,
    "agent_prompt_stalled.json": CONSTRUCTED,
    "timeout.json": CONSTRUCTED,
    "pane_split.json": CONSTRUCTED,
    "agent_started.json": CONSTRUCTED,
    "agent_prompted.json": CONSTRUCTED,
    "ok.json": CONSTRUCTED,
    "agent_list.json": CONSTRUCTED,
    "agent_list_path.json": CONSTRUCTED,
    "agent_list_null_session.json": CONSTRUCTED,
    "agent_list_no_match.json": CONSTRUCTED,
    "process_info.json": CONSTRUCTED,
    "process_info_no_shell.json": CONSTRUCTED,
}

NAME = "t7-builder-1"
PANE = "w1:p2"
SHELL_PID = 1000


# --- harness ------------------------------------------------------------------


def reply(name: str) -> CommandResult:
    """A stored reply as the CLI would give it: errors on stderr with exit 1."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    if name.endswith(".txt"):
        return CommandResult(0, text, "")
    if "error" in json.loads(text):
        return CommandResult(1, "", text)
    return CommandResult(0, text, "")


def screen(name: str) -> CommandResult:
    """`agent read` answering with a stored screen."""
    text = (FIXTURES / name).read_text(encoding="utf-8")
    body = {
        "id": "cli:agent:read",
        "result": {
            "type": "pane_read",
            "read": {"pane_id": PANE, "text": text, "truncated": False},
        },
    }
    return CommandResult(0, json.dumps(body), "")


class ScriptedHerdr:
    """
    Answers each command from a script, one reply per call, repeating the last.

    A command nobody scripted fails the test: an unexpected herdr command is
    exactly what these tests exist to catch.
    """

    def __init__(self, script: Mapping[str, Sequence[CommandResult | str]]) -> None:
        self.script = {
            key: [reply(r) if isinstance(r, str) else r for r in value]
            for key, value in script.items()
        }
        self.calls: list[list[str]] = []
        self._seen: dict[str, int] = {}

    def __call__(self, args: Sequence[str]) -> CommandResult:
        self.calls.append(list(args))
        assert args[0] == "herdr", args
        key = " ".join(args[1:3])
        assert key in self.script, f"unscripted herdr command: {list(args)}"
        index = self._seen.get(key, 0)
        self._seen[key] = index + 1
        replies = self.script[key]
        return replies[min(index, len(replies) - 1)]

    def commands(self) -> list[str]:
        return [" ".join(c[1:3]) for c in self.calls]

    def sent_keys(self) -> list[list[str]]:
        return [c for c in self.calls if c[1:3] == ["agent", "send-keys"]]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture(autouse=True)
def no_real_herdr(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(args: Sequence[str]) -> CommandResult:
        raise AssertionError(f"a test reached the real herdr binary: {list(args)}")

    monkeypatch.setattr(herdr_module, "default_runner", refuse)


@dataclasses.dataclass
class Repo:
    common_dir: Path
    worktree: Path
    plain: Path


def _link_worktree(
    root: Path,
    *,
    relative: bool = False,
    outside: bool = False,
    backpointer: str = "posix",
) -> Path:
    """Lay out a linked worktree the way git does, with variations."""
    common = root / "main" / ".git"
    worktree = root / "wt"
    worktree.mkdir(parents=True, exist_ok=True)
    parent = root / "elsewhere" if outside else common / "worktrees"
    admin = parent / "wt"
    admin.mkdir(parents=True, exist_ok=True)
    target = Path(os.path.relpath(admin, worktree)) if relative else admin
    (worktree / ".git").write_text(f"gitdir: {target.as_posix()}\n", encoding="utf-8")
    dot_git = worktree / ".git"
    if backpointer == "posix":
        # Git writes forward slashes, even on Windows.
        (admin / "gitdir").write_text(dot_git.as_posix() + "\n", encoding="utf-8")
    elif backpointer == "native":
        (admin / "gitdir").write_text(str(dot_git) + "\n", encoding="utf-8")
    elif backpointer == "wrong":
        other = root / "other" / ".git"
        (admin / "gitdir").write_text(other.as_posix() + "\n", encoding="utf-8")
    return worktree


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    worktree = _link_worktree(tmp_path)
    plain = tmp_path / "plain"
    plain.mkdir()
    return Repo(tmp_path / "main" / ".git", worktree, plain)


def spec_for(
    repo: Repo, *, role: str = "builder", cwd: Path | None = None, **over: object
) -> WorkerSpec:
    kwargs: dict[str, typing.Any] = {
        "role": role,
        "stage": "build",
        "ticket": 7,
        "name": NAME,
        "cwd": cwd or repo.worktree,
        "model": "sonnet",
        "prompt": "do the thing",
        "common_dir": repo.common_dir,
    }
    kwargs.update(over)
    return worker_spec(**kwargs)


def launcher_for(
    repo: Repo,
    herdr: ScriptedHerdr,
    *,
    table: Callable[[], Mapping[int, int]] | None = None,
    environ: Mapping[str, str] | None = None,
    clock: Clock | None = None,
) -> HerdrLauncher:
    clock = clock or Clock()
    return HerdrLauncher(
        repo.common_dir,
        run=herdr,
        read_process_table=table or dict,
        environ=environ if environ is not None else {},
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )


NEW = ["agent_not_found.json"]
HAPPY: dict[str, list[CommandResult | str]] = {
    "agent get": [*NEW],
    "pane split": ["pane_split.json"],
    "agent start": ["agent_started.json"],
    "agent prompt": ["agent_prompted.json"],
}


def script(
    **over: Sequence[CommandResult | str],
) -> dict[str, Sequence[CommandResult | str]]:
    merged: dict[str, Sequence[CommandResult | str]] = dict(HAPPY)
    merged.update({k.replace("_", " ", 1): v for k, v in over.items()})
    return merged


def blocked_startup(
    *, dialog: str | CommandResult = "trust-dialog-live.txt", **over: Sequence[str]
) -> dict[str, Sequence[CommandResult | str]]:
    """The startup the trust dialog blocks, answered, and then settling idle."""
    screen_reply = screen(dialog) if isinstance(dialog, str) else dialog
    base: dict[str, Sequence[CommandResult | str]] = {
        "agent get": [*NEW, "agent_get_blocked.json", "agent_get_idle.json"],
        "pane split": ["pane_split.json"],
        "agent start": ["agent_not_ready.json"],
        "agent read": [screen_reply],
        "agent send-keys": ["ok.json"],
        "agent wait": ["ok.json"],
        "agent prompt": ["agent_prompted.json"],
    }
    base.update({k.replace("_", " ", 1): v for k, v in over.items()})
    return base


def handle_for(spec: WorkerSpec, *, seen: bool = False) -> Handle:
    return Handle(spec.name, PANE, spec.env["FACTORY_ROLE"], seen)


def start_error(launcher: HerdrLauncher, spec: WorkerSpec) -> LauncherError:
    with pytest.raises(LauncherError) as caught:
        launcher.start(spec)
    return caught.value


# --- stored replies -----------------------------------------------------------


def test_every_stored_reply_says_where_it_came_from() -> None:
    stored = {p.name for p in FIXTURES.iterdir() if p.is_file()}
    assert stored == set(PROVENANCE)
    assert set(PROVENANCE.values()) <= {CAPTURED, CONSTRUCTED}
    assert HERDR_VERSION == "0.9.5"


def test_the_guard_fails_a_test_that_reaches_the_real_binary(repo: Repo) -> None:
    launcher = HerdrLauncher(repo.common_dir)
    with pytest.raises(AssertionError, match="real herdr"):
        launcher.status(Handle(NAME, PANE, "builder", True))


# --- start: the command sequence ----------------------------------------------


def test_start_issues_split_agent_start_and_prompt_in_order(repo: Repo) -> None:
    herdr = ScriptedHerdr(script())
    spec = spec_for(repo)
    handle = launcher_for(repo, herdr).start(spec)
    assert handle == Handle(NAME, PANE, "builder", True)
    timeouts = Timeouts()
    expected_env = [f"{k}={v}" for k, v in spec.env.items()]
    assert any(e == "GITHUB_TOKEN=" for e in expected_env)
    assert herdr.calls == [
        ["herdr", "agent", "get", NAME],
        [
            "herdr",
            "pane",
            "split",
            "--no-focus",
            "--cwd",
            str(repo.worktree),
            *[x for e in expected_env for x in ("--env", e)],
        ],
        [
            "herdr",
            "agent",
            "start",
            NAME,
            "--kind",
            "claude",
            "--pane",
            PANE,
            "--timeout",
            str(timeouts.agent_start_ms),
            "--",
            "--model",
            "sonnet",
        ],
        [
            "herdr",
            "agent",
            "prompt",
            PANE,
            "do the thing",
            "--wait",
            "--until",
            "working",
            "--until",
            "blocked",
            "--timeout",
            str(timeouts.agent_prompt_ms),
        ],
    ]


def test_start_passes_resume_only_when_it_is_set(repo: Repo) -> None:
    herdr = ScriptedHerdr(script())
    spec = spec_for(repo, role="designer", resume="sess-1")
    launcher_for(repo, herdr).start(spec)
    start = next(c for c in herdr.calls if c[1:3] == ["agent", "start"])
    assert start[start.index("--") :] == [
        "--",
        "--model",
        "sonnet",
        "--resume",
        "sess-1",
    ]


def test_start_does_not_put_double_dash_before_the_prompt(repo: Repo) -> None:
    herdr = ScriptedHerdr(script())
    launcher_for(repo, herdr).start(spec_for(repo, prompt="-x"))
    prompt = herdr.calls[-1]
    assert "--" not in prompt
    assert prompt[3:5] == [PANE, "-x"]


def test_a_second_start_on_the_same_launcher_returns_the_first_handle(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(script())
    launcher = launcher_for(repo, herdr)
    spec = spec_for(repo)
    first = launcher.start(spec)
    issued = len(herdr.calls)
    assert launcher.start(spec) == first
    assert len(herdr.calls) == issued


def test_a_fresh_launcher_that_finds_the_agent_starts_nothing(repo: Repo) -> None:
    herdr = ScriptedHerdr({"agent get": ["agent_get_idle.json"]})
    handle = launcher_for(repo, herdr).start(spec_for(repo))
    assert herdr.calls == [["herdr", "agent", "get", NAME]]
    assert handle == Handle(NAME, PANE, "builder", False)


def test_a_replayed_start_is_remembered_by_the_launcher_that_found_it(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr({"agent get": ["agent_get_idle.json"]})
    launcher = launcher_for(repo, herdr)
    first = launcher.start(spec_for(repo))
    assert launcher.start(spec_for(repo)) == first
    assert len(herdr.calls) == 1


def test_an_agent_get_error_other_than_not_found_starts_nothing(repo: Repo) -> None:
    herdr = ScriptedHerdr({"agent get": ["error_other.json"]})
    error = start_error(launcher_for(repo, herdr), spec_for(repo))
    assert error.handle is None
    assert herdr.commands() == ["agent get"]


def test_start_refuses_missing_credentials_before_any_command(repo: Repo) -> None:
    herdr = ScriptedHerdr(script())
    spec = spec_for(repo)
    env = {k: v for k, v in spec.env.items() if k != "GITHUB_TOKEN"}
    with pytest.raises(LauncherError, match="GITHUB_TOKEN"):
        launcher_for(repo, herdr).start(dataclasses.replace(spec, env=env))
    assert herdr.calls == []


def test_a_failed_split_leaves_no_handle(repo: Repo) -> None:
    herdr = ScriptedHerdr(script(pane_split=["error_other.json"]))
    error = start_error(launcher_for(repo, herdr), spec_for(repo))
    assert error.handle is None
    assert herdr.commands() == ["agent get", "pane split"]


# --- start: failures after the split carry the handle -------------------------


@pytest.mark.parametrize("failure", ["timeout.json", "error_other.json"])
def test_an_agent_start_failure_carries_the_handle_and_sends_nothing(
    repo: Repo, failure: str
) -> None:
    herdr = ScriptedHerdr(script(agent_start=[failure]))
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert herdr.commands() == ["agent get", "pane split", "agent start"]


@pytest.mark.parametrize(
    "failure", ["agent_prompt_stalled.json", "timeout.json", "error_other.json"]
)
def test_a_prompt_failure_carries_the_handle(repo: Repo, failure: str) -> None:
    herdr = ScriptedHerdr(script(agent_prompt=[failure]))
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert herdr.sent_keys() == []


def test_a_state_other_than_blocked_after_not_ready_raises_without_reading(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(
        blocked_startup(agent_get=[*NEW, "agent_get_idle.json"]),
    )
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert "agent read" not in herdr.commands()
    assert herdr.sent_keys() == []
    assert "agent prompt" not in herdr.commands()


# --- the trust dialog ---------------------------------------------------------


def test_the_live_trust_dialog_is_answered_once_and_the_prompt_then_sent(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(blocked_startup())
    spec = spec_for(repo)
    handle = launcher_for(repo, herdr).start(spec)
    assert handle == handle_for(spec, seen=True)
    timeouts = Timeouts()
    assert herdr.calls[3:] == [
        ["herdr", "agent", "get", PANE],
        ["herdr", "agent", "read", PANE, "--source", "recent-unwrapped"],
        ["herdr", "agent", "send-keys", PANE, "down", "enter"],
        [
            "herdr",
            "agent",
            "wait",
            PANE,
            "--until",
            "idle",
            "--until",
            "done",
            "--until",
            "blocked",
            "--timeout",
            str(timeouts.trust_wait_ms),
        ],
        ["herdr", "agent", "get", PANE],
        herdr.calls[-1],
    ]
    assert herdr.calls[-1][1:4] == ["agent", "prompt", PANE]
    for command in herdr.calls[3:]:
        assert command[3] == PANE


def test_a_numbered_layout_with_consecutive_numbers_is_answered(repo: Repo) -> None:
    herdr = ScriptedHerdr(blocked_startup(dialog="trust-dialog-numbered.txt"))
    launcher_for(repo, herdr).start(spec_for(repo))
    assert len(herdr.sent_keys()) == 1


def test_a_done_state_after_the_answer_also_allows_the_prompt(repo: Repo) -> None:
    herdr = ScriptedHerdr(
        blocked_startup(
            agent_get=[*NEW, "agent_get_blocked.json", "agent_get_done.json"]
        )
    )
    launcher_for(repo, herdr).start(spec_for(repo))
    assert herdr.commands()[-1] == "agent prompt"


def test_the_trust_dialog_outside_a_linked_worktree_is_not_answered(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(blocked_startup())
    spec = spec_for(repo, cwd=repo.plain)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert herdr.sent_keys() == []
    assert "agent prompt" not in herdr.commands()


@pytest.mark.parametrize(
    "dialog",
    [
        "trust-dialog-yes-first.txt",
        "trust-dialog-cursor-on-yes.txt",
        "trust-dialog-between.txt",
        "trust-dialog-numbered-gap.txt",
        "trust-dialog-no-question.txt",
    ],
)
def test_the_trust_dialog_in_any_other_layout_is_not_answered(
    repo: Repo, dialog: str
) -> None:
    herdr = ScriptedHerdr(blocked_startup(dialog=dialog))
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert herdr.sent_keys() == []
    assert "agent prompt" not in herdr.commands()


def test_any_other_blocked_screen_is_not_answered(repo: Repo) -> None:
    herdr = ScriptedHerdr(blocked_startup(dialog="blocked-mcp-approval.txt"))
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert herdr.sent_keys() == []
    assert "agent prompt" not in herdr.commands()


def test_a_blocked_state_after_the_answer_raises_after_one_answer(repo: Repo) -> None:
    herdr = ScriptedHerdr(
        blocked_startup(
            agent_get=[*NEW, "agent_get_blocked.json", "agent_get_blocked.json"]
        )
    )
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert len(herdr.sent_keys()) == 1
    assert "agent prompt" not in herdr.commands()


@pytest.mark.parametrize("step", ["agent wait", "agent get"])
def test_agent_not_found_after_the_answer_raises_after_one_answer(
    repo: Repo, step: str
) -> None:
    scripted = blocked_startup()
    if step == "agent wait":
        scripted["agent wait"] = ["agent_not_found.json"]
    else:
        scripted["agent get"] = [*NEW, "agent_get_blocked.json", "agent_not_found.json"]
    herdr = ScriptedHerdr(scripted)
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert len(herdr.sent_keys()) == 1
    assert "agent prompt" not in herdr.commands()


@pytest.mark.parametrize(
    "failure", ["agent_prompt_stalled.json", "timeout.json", "error_other.json"]
)
def test_a_prompt_failure_after_the_answer_sends_no_second_answer(
    repo: Repo, failure: str
) -> None:
    herdr = ScriptedHerdr(blocked_startup(agent_prompt=[failure]))
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert len(herdr.sent_keys()) == 1


def test_a_failed_screen_read_raises_with_the_handle(repo: Repo) -> None:
    herdr = ScriptedHerdr(blocked_startup(agent_read=["agent_not_found.json"]))
    spec = spec_for(repo)
    error = start_error(launcher_for(repo, herdr), spec)
    assert error.handle == handle_for(spec)
    assert herdr.sent_keys() == []


# --- the dialog matcher -------------------------------------------------------


def _fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_the_live_screen_matches() -> None:
    assert trust_dialog_matches(_fixture_text("trust-dialog-live.txt"))


def test_a_narrow_pane_wrapping_the_question_cannot_hide_it() -> None:
    live = _fixture_text("trust-dialog-live.txt")
    wrapped = live.replace("Is this a project", "Is this a\n project").replace(
        "you trust?", "you\n   trust?"
    )
    assert trust_dialog_matches(wrapped)


@pytest.mark.parametrize(
    "name",
    [
        "trust-dialog-yes-first.txt",
        "trust-dialog-cursor-on-yes.txt",
        "trust-dialog-between.txt",
        "trust-dialog-numbered-gap.txt",
        "trust-dialog-no-question.txt",
        "blocked-mcp-approval.txt",
    ],
)
def test_other_screens_do_not_match(name: str) -> None:
    assert not trust_dialog_matches(_fixture_text(name))


def test_numbers_on_one_option_only_do_not_match() -> None:
    live = _fixture_text("trust-dialog-live.txt")
    assert not trust_dialog_matches(live.replace("❯ No, exit", "❯ 1. No, exit"))
    assert not trust_dialog_matches(live.replace("Yes, I trust", "2. Yes, I trust"))


# --- the linked-worktree check ------------------------------------------------


@pytest.mark.parametrize("backpointer", ["posix", "native"])
def test_a_linked_worktree_is_recognised_whichever_way_the_backpointer_is_written(
    tmp_path: Path, backpointer: str
) -> None:
    worktree = _link_worktree(tmp_path, backpointer=backpointer)
    assert is_linked_worktree(worktree, tmp_path / "main" / ".git")


def test_a_relative_gitdir_is_resolved_against_the_worktree(tmp_path: Path) -> None:
    worktree = _link_worktree(tmp_path, relative=True)
    assert (worktree / ".git").read_text().startswith("gitdir: ..")
    assert is_linked_worktree(worktree, tmp_path / "main" / ".git")


def test_a_gitdir_outside_the_worktrees_directory_is_refused(tmp_path: Path) -> None:
    worktree = _link_worktree(tmp_path, outside=True)
    assert not is_linked_worktree(worktree, tmp_path / "main" / ".git")


@pytest.mark.parametrize("backpointer", ["missing", "wrong"])
def test_a_missing_or_mismatched_backpointer_is_refused(
    tmp_path: Path, backpointer: str
) -> None:
    worktree = _link_worktree(tmp_path, backpointer=backpointer)
    assert not is_linked_worktree(worktree, tmp_path / "main" / ".git")


def test_a_worktree_of_another_repository_is_refused(tmp_path: Path) -> None:
    worktree = _link_worktree(tmp_path)
    other = tmp_path / "other" / ".git"
    other.mkdir(parents=True)
    assert not is_linked_worktree(worktree, other)


def test_a_main_checkout_and_a_bare_directory_are_refused(tmp_path: Path) -> None:
    main = tmp_path / "main"
    (main / ".git").mkdir(parents=True)
    assert not is_linked_worktree(main, main / ".git")
    assert not is_linked_worktree(tmp_path, main / ".git")


# --- status -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "seen", "expected"),
    [
        ("agent_get_working.json", True, WorkerState.WORKING),
        ("agent_get_unknown.json", True, WorkerState.WORKING),
        ("agent_get_idle.json", True, WorkerState.FINISHED),
        ("agent_get_done.json", True, WorkerState.FINISHED),
        ("agent_get_blocked.json", True, WorkerState.BLOCKED),
        ("agent_not_found.json", True, WorkerState.GONE),
        ("agent_get_working.json", False, WorkerState.WORKING),
        ("agent_get_idle.json", False, WorkerState.BLOCKED),
        ("agent_get_done.json", False, WorkerState.BLOCKED),
        ("agent_get_blocked.json", False, WorkerState.BLOCKED),
    ],
)
def test_status_maps_each_herdr_state(
    repo: Repo, stored: str, seen: bool, expected: WorkerState
) -> None:
    herdr = ScriptedHerdr({"agent get": [stored]})
    handle = Handle(NAME, PANE, "builder", seen)
    assert launcher_for(repo, herdr).status(handle) is expected
    assert herdr.calls == [["herdr", "agent", "get", PANE]]


@pytest.mark.parametrize(
    "stored", ["error_other.json", "not_json.txt", "agent_get_sleeping.json"]
)
def test_status_raises_for_anything_it_cannot_map(repo: Repo, stored: str) -> None:
    herdr = ScriptedHerdr({"agent get": [stored]})
    with pytest.raises(LauncherError):
        launcher_for(repo, herdr).status(Handle(NAME, PANE, "builder", True))


def test_a_reply_that_is_not_json_raises_wherever_it_arrives(repo: Repo) -> None:
    herdr = ScriptedHerdr(script(pane_split=["not_json.txt"]))
    error = start_error(launcher_for(repo, herdr), spec_for(repo))
    assert error.handle is None


# --- session_id ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("agent_list.json", "sess-1234"),
        ("agent_list_path.json", None),
        ("agent_list_null_session.json", None),
        ("agent_list_no_match.json", None),
    ],
)
def test_session_id_reads_the_entry_for_the_handles_pane(
    repo: Repo, stored: str, expected: str | None
) -> None:
    herdr = ScriptedHerdr({"agent list": [stored]})
    handle = Handle(NAME, PANE, "builder", True)
    assert launcher_for(repo, herdr).session_id(handle) == expected
    assert herdr.calls == [["herdr", "agent", "list"]]


# --- stop ---------------------------------------------------------------------

TREE = {5: 1, SHELL_PID: 5, 1001: SHELL_PID, 1002: 1001, 1003: 1002}
GONE = {5: 1}


def stop_script(
    **over: Sequence[CommandResult | str],
) -> dict[str, Sequence[CommandResult | str]]:
    base: dict[str, Sequence[CommandResult | str]] = {
        "pane process-info": ["process_info.json"],
        "pane close": ["ok.json"],
    }
    base.update(
        {
            k.replace("_", " ", 1).replace("process_info", "process-info"): v
            for k, v in over.items()
        }
    )
    return base


def tables(*snapshots: Mapping[int, int]) -> Callable[[], Mapping[int, int]]:
    queue = list(snapshots)

    def read() -> Mapping[int, int]:
        return queue.pop(0) if len(queue) > 1 else queue[0]

    return read


def test_stop_closes_only_the_handles_pane_and_waits_for_the_tree(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    clock = Clock()
    launcher = launcher_for(
        repo, herdr, table=tables(TREE, TREE, {5: 1, 1003: 1002}, GONE), clock=clock
    )
    launcher.stop(Handle(NAME, PANE, "builder", True))
    assert herdr.calls == [
        ["herdr", "pane", "process-info", "--pane", PANE],
        ["herdr", "pane", "close", PANE],
    ]
    assert len(clock.sleeps) == 2


def test_stop_raises_when_a_descendant_outlives_the_timeout(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    still = {5: 1, 1003: 1002}
    launcher = launcher_for(repo, herdr, table=tables(TREE, still))
    with pytest.raises(LauncherError, match="1003"):
        launcher.stop(Handle(NAME, PANE, "builder", True))


def test_stop_raises_when_the_shell_itself_survives(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    launcher = launcher_for(repo, herdr, table=tables(TREE, TREE))
    with pytest.raises(LauncherError, match=str(SHELL_PID)):
        launcher.stop(Handle(NAME, PANE, "builder", True))


def test_after_stop_returns_status_is_gone(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    launcher = launcher_for(repo, herdr, table=tables(TREE, GONE))
    handle = Handle(NAME, PANE, "builder", True)
    launcher.stop(handle)
    issued = len(herdr.calls)
    assert launcher.status(handle) is WorkerState.GONE
    assert len(herdr.calls) == issued


def test_a_failed_stop_does_not_make_status_gone(repo: Repo) -> None:
    herdr = ScriptedHerdr({**stop_script(), "agent get": ["agent_get_working.json"]})
    launcher = launcher_for(repo, herdr, table=tables(TREE, TREE))
    handle = Handle(NAME, PANE, "builder", True)
    with pytest.raises(LauncherError):
        launcher.stop(handle)
    assert launcher.status(handle) is WorkerState.WORKING


def test_stop_refuses_a_designer_and_issues_nothing(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    launcher = launcher_for(repo, herdr, table=tables(TREE, GONE))
    with pytest.raises(LauncherError, match="designer"):
        launcher.stop(Handle("d", PANE, "designer", True))
    assert herdr.calls == []


def test_stop_refuses_the_launchers_own_pane_and_issues_nothing(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    launcher = launcher_for(
        repo, herdr, table=tables(TREE, GONE), environ={"HERDR_PANE_ID": PANE}
    )
    with pytest.raises(LauncherError, match="own pane"):
        launcher.stop(Handle(NAME, PANE, "builder", True))
    assert herdr.calls == []


def test_a_pane_herdr_no_longer_has_counts_as_stopped_and_stop_is_repeatable(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(stop_script(pane_process_info=["pane_not_found.json"]))
    launcher = launcher_for(repo, herdr)
    handle = Handle(NAME, PANE, "builder", True)
    launcher.stop(handle)
    launcher.stop(handle)
    assert herdr.commands() == ["pane process-info", "pane process-info"]
    assert launcher.status(handle) is WorkerState.GONE


def test_stop_raises_before_closing_when_herdr_reports_no_shell_pid(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(stop_script(pane_process_info=["process_info_no_shell.json"]))
    launcher = launcher_for(repo, herdr, table=tables(TREE))
    with pytest.raises(LauncherError, match="shell_pid"):
        launcher.stop(Handle(NAME, PANE, "builder", True))
    assert "pane close" not in herdr.commands()


def test_stop_cannot_pass_on_an_empty_process_table(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script())
    launcher = launcher_for(repo, herdr, table=tables({}))
    with pytest.raises(LauncherError, match=str(SHELL_PID)):
        launcher.stop(Handle(NAME, PANE, "builder", True))
    assert "pane close" not in herdr.commands()


def test_a_process_info_error_other_than_not_found_raises_without_closing(
    repo: Repo,
) -> None:
    herdr = ScriptedHerdr(stop_script(pane_process_info=["error_other.json"]))
    with pytest.raises(LauncherError):
        launcher_for(repo, herdr, table=tables(TREE)).stop(
            Handle(NAME, PANE, "builder", True)
        )
    assert "pane close" not in herdr.commands()


def test_a_close_error_raises(repo: Repo) -> None:
    herdr = ScriptedHerdr(stop_script(pane_close=["error_other.json"]))
    with pytest.raises(LauncherError):
        launcher_for(repo, herdr, table=tables(TREE, GONE)).stop(
            Handle(NAME, PANE, "builder", True)
        )


# --- the default process-table reader -----------------------------------------


@pytest.mark.skipif(sys.platform != "win32", reason="Toolhelp is Windows only")
def test_the_default_reader_lists_this_process_with_its_parent() -> None:
    table = read_process_table()
    assert table[os.getpid()] == os.getppid()


def test_the_default_reader_raises_on_any_other_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(NotImplementedError):
        read_process_table()


def test_importing_the_adapter_never_raises_on_another_platform() -> None:
    code = (
        "import sys; sys.platform = 'linux'; "
        "import factory.launchers.herdr as m; "
        "sys.exit(0 if callable(m.read_process_table) else 1)"
    )
    done = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
