"""
What Stop judges: the session's own worktree, plus what it wrote (#207).

Real temporary git repositories, because the base and the change set are git's
answers and a fabricated `.git` directory cannot give them. Every repository
here is built by `git init` with a fixed identity, no signing and an empty hooks
directory, so nothing on the machine leaks in.

`origin` is simulated without a remote: `refs/remotes/origin/dev` is a ref we
move by hand, and `origin/HEAD` points at it. That is exactly what a fetch
leaves behind, and it lets a test move "the default branch" at will.
"""

from __future__ import annotations

import inspect
import io
import json
import subprocess
import threading
from pathlib import Path
from typing import Any

import pytest

from factory import cli, worktrees
from factory.cli import main as main_cli
from factory.exit_codes import ExitCode

PROVEN = "---\nticket: {n}\nproof:\n  suite: pass\n---\n"
UNPROVEN = "---\nticket: {n}\nproof:\n  suite: null\n---\n"


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def _configure(root: Path) -> None:
    hooks = root.parent / "no-hooks"
    hooks.mkdir(exist_ok=True)
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(hooks)),
    ):
        git(root, "config", key, value)


def commit(root: Path, files: dict[str, str], message: str = "work") -> str:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def set_default_branch(root: Path, sha: str) -> None:
    """What a fetch leaves: `origin/dev` at `sha`, and `origin/HEAD` -> it."""
    git(root, "update-ref", "refs/remotes/origin/dev", sha)
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/dev")


@pytest.fixture
def main(tmp_path: Path) -> Path:
    """A primary checkout on `dev`, with `origin/HEAD` on its one commit."""
    root = (tmp_path / "main").resolve()
    root.mkdir()
    git(root, "init", "-q", "-b", "dev")
    _configure(root)
    set_default_branch(root, commit(root, {"a.py": "a\n"}, "c1"))
    return root


def ticket(main: Path, n: int, start: str = "dev", slug: str = "x") -> Path:
    """A linked worktree on `issue/<n>-<slug>`, with the chain committed first."""
    root = main.parent / f"wt{n}"
    git(main, "worktree", "add", "-q", "-b", f"issue/{n}-{slug}", str(root), start)
    commit(
        root,
        {
            f".factory/{n}/intent.md": "intent\n",
            f".factory/{n}/spec.md": "---\nticket: 1\n---\n",
            f".factory/{n}/spec-review.md": "---\nverdict: pass\n---\n",
        },
        f"artifacts for {n}",
    )
    return root


def run_hook(
    event: str,
    payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, Any]:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    assert main_cli(["hook", event]) == ExitCode.OK
    out = capsys.readouterr().out
    return json.loads(out) if out.strip() else {}


def sessions_dir(main: Path, session_id: str) -> Path:
    return main / ".git" / "factory" / "sessions" / session_id


def write_event(
    session: Path, target: Path, session_id: object = "s1"
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "cwd": str(session),
        "tool_input": {"file_path": str(target)},
    }
    if session_id is not None:
        event["session_id"] = session_id
    return event


# --- Committed source is source ----------------------------------------------


def test_committed_source_with_no_plan_is_refused(main: Path) -> None:
    """Today only the working tree is read, so committing first escaped the gate."""
    wt = ticket(main, 1)
    commit(wt, {"src.py": "x = 1\n"})
    assert not cli._stop_everywhere(wt).allowed


def test_committed_source_with_a_plan_but_no_proof_is_refused(main: Path) -> None:
    wt = ticket(main, 1)
    commit(wt, {"src.py": "x = 1\n", ".factory/1/plan.md": UNPROVEN.format(n=1)})
    decision = cli._stop_everywhere(wt)
    assert not decision.allowed
    assert "proof" in decision.reason


def test_a_proven_ticket_stops_cleanly(main: Path) -> None:
    wt = ticket(main, 1)
    commit(wt, {"src.py": "x = 1\n", ".factory/1/plan.md": PROVEN.format(n=1)})
    assert cli._stop_everywhere(wt).allowed


def test_the_refusal_names_the_worktree_the_ticket_and_the_base(main: Path) -> None:
    wt = ticket(main, 1)
    base = git(main, "rev-parse", "dev")
    commit(wt, {"src.py": "x = 1\n"})
    reason = cli._stop_everywhere(wt).reason
    assert str(wt) in reason
    assert "ticket 1" in reason.lower()
    assert base in reason


def test_a_refusal_with_no_base_says_so(tmp_path: Path) -> None:
    root = _solo(tmp_path)
    (root / "src.py").write_text("x\n", encoding="utf-8")
    reason = cli._stop_everywhere(root).reason
    assert str(root) in reason
    assert "no base" in reason.lower()


# --- The base ----------------------------------------------------------------


def test_the_base_is_the_parent_of_the_first_chain_commit(main: Path) -> None:
    wt = ticket(main, 1)
    commit(wt, {"src.py": "x = 1\n"})
    assert cli._base(wt) == git(main, "rev-parse", "dev")
    assert cli._changed_paths(wt) == {"src.py"}


def test_a_stacked_branch_is_judged_on_its_own_commits(main: Path) -> None:
    one = ticket(main, 1)
    commit(one, {"one.py": "1\n", ".factory/1/plan.md": PROVEN.format(n=1)})
    tip = git(one, "rev-parse", "HEAD")
    two = ticket(main, 2, start="issue/1-x")
    assert cli._base(two) == tip
    assert cli._changed_paths(two) == set(), "the parent ticket's source is not ours"
    assert cli._stop_everywhere(two).allowed
    commit(two, {"two.py": "2\n"})
    assert cli._changed_paths(two) == {"two.py"}
    assert not cli._stop_everywhere(two).allowed


def test_the_default_branch_moving_after_the_branch_was_cut(main: Path) -> None:
    wt = ticket(main, 1)
    cut = git(main, "rev-parse", "dev")
    commit(wt, {"src.py": "x = 1\n"})
    set_default_branch(main, commit(main, {"dev_only.py": "d\n"}, "dev moves"))
    assert cli._base(wt) == cut
    assert cli._changed_paths(wt) == {"src.py"}


def test_a_pushed_branch_is_judged_the_same(main: Path) -> None:
    wt = ticket(main, 1)
    commit(wt, {"src.py": "x = 1\n"})
    git(main, "update-ref", "refs/remotes/origin/issue/1-x", "issue/1-x")
    assert cli._changed_paths(wt) == {"src.py"}
    assert not cli._stop_everywhere(wt).allowed


def test_a_child_branch_cut_below_the_parent_s_tip(main: Path) -> None:
    one = ticket(main, 1)
    commit(one, {"one.py": "1\n"})
    commit(one, {"one_b.py": "1b\n"})
    two = ticket(main, 2, start="issue/1-x~1")
    assert cli._base(two) == git(one, "rev-parse", "HEAD~1")
    assert cli._changed_paths(two) == set()


def test_the_default_branch_merged_in_is_not_the_ticket_s_source(main: Path) -> None:
    """
    Note a of spec review 3. `dev`'s own files arrive through the merge, and
    `f^` is older than the merge-base, so the later of the two is the base.
    """
    wt = ticket(main, 1)
    commit(wt, {"own.py": "own\n"})
    new_tip = commit(main, {"dev_only.py": "d\n"}, "dev moves")
    set_default_branch(main, new_tip)
    git(wt, "merge", "-q", "--no-edit", "dev")
    assert cli._base(wt) == new_tip
    assert cli._changed_paths(wt) == {"own.py"}


def test_a_chain_that_already_sits_on_the_default_branch(main: Path) -> None:
    """Note c: the chain was committed on `dev`, then `dev` moved on."""
    commit(main, {".factory/5/intent.md": "i\n", ".factory/5/spec.md": "s\n"}, "chain")
    tip = commit(main, {"dev_only.py": "d\n"}, "dev moves on")
    set_default_branch(main, tip)
    root = main.parent / "wt5"
    git(main, "worktree", "add", "-q", "-b", "issue/5-x", str(root), "dev")
    commit(root, {"src.py": "x\n"})
    assert cli._base(root) == tip
    assert cli._changed_paths(root) == {"src.py"}


def _solo(tmp_path: Path) -> Path:
    """A repository whose first commit is the chain: a chain commit with no parent."""
    root = (tmp_path / "solo").resolve()
    root.mkdir()
    git(root, "init", "-q", "-b", "issue/6-x")
    _configure(root)
    commit(root, {".factory/6/intent.md": "intent\n"})
    return root


def test_a_chain_commit_with_no_parent_falls_back_to_the_default_branch(
    tmp_path: Path,
) -> None:
    root = _solo(tmp_path)
    set_default_branch(root, git(root, "rev-parse", "HEAD"))
    commit(root, {"src.py": "x\n"})
    (root / "u.py").write_text("u\n", encoding="utf-8")
    assert cli._base(root) == git(root, "rev-parse", "HEAD~1")
    assert cli._changed_paths(root) == {"src.py", "u.py"}


def test_with_no_base_only_the_uncommitted_paths_are_judged(tmp_path: Path) -> None:
    root = _solo(tmp_path)
    commit(root, {"src.py": "x\n"})
    (root / "u.py").write_text("u\n", encoding="utf-8")
    assert cli._base(root) is None
    assert cli._changed_paths(root) == {"u.py"}


def test_the_factory_directory_is_never_in_the_change_set(main: Path) -> None:
    wt = ticket(main, 1)
    commit(wt, {".factory/1/plan.md": UNPROVEN.format(n=1)})
    (wt / ".factory" / "1" / "more.md").write_text("m\n", encoding="utf-8")
    assert cli._changed_paths(wt) == set()


def test_no_branch_name_appears_in_the_base_or_the_change_set() -> None:
    for function in (cli._base, cli._changed_paths, cli._source_changed):
        source = inspect.getsource(function)
        assert "issue/" not in source
        assert "movements-improvements" not in source


# --- Session start -----------------------------------------------------------


def test_session_start_says_the_committed_range_is_not_checked_without_a_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _solo(tmp_path)
    answer = run_hook("session-start", {"cwd": str(root)}, monkeypatch, capsys)
    context = answer["hookSpecificOutput"]["additionalContext"]
    assert "not checked" in context
    assert "git remote set-head origin --auto" in context


def test_session_start_is_quiet_about_it_when_a_base_resolves(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    wt = ticket(main, 1)
    answer = run_hook("session-start", {"cwd": str(wt)}, monkeypatch, capsys)
    context = answer["hookSpecificOutput"]["additionalContext"]
    assert "set-head" not in context


# --- Who is judged -----------------------------------------------------------


def test_a_session_that_wrote_another_worktree_is_judged_on_both(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    wrote = run_hook("pre-tool-use", write_event(a, b / "src.py"), monkeypatch, capsys)
    assert wrote == {}
    commit(b, {"src.py": "x\n"})

    answer = run_hook("stop", {"cwd": str(a), "session_id": "s1"}, monkeypatch, capsys)
    assert answer["decision"] == "block"
    assert str(b) in answer["reason"]


def test_an_unrelated_worktree_mid_build_does_not_block_the_session(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    (b / "src.py").write_text("mid-build\n", encoding="utf-8")
    event = {"cwd": str(a), "session_id": "s1"}
    assert run_hook("stop", event, monkeypatch, capsys) == {}


def test_a_session_on_no_ticket_that_wrote_nowhere_stops_cleanly(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    b = ticket(main, 2)
    (b / "src.py").write_text("mid-build\n", encoding="utf-8")
    event = {"cwd": str(main), "session_id": "s1"}
    assert run_hook("stop", event, monkeypatch, capsys) == {}


def test_the_primary_checkout_on_a_ticket_branch_is_judged_on_what_it_wrote(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    b = ticket(main, 2)
    git(main, "checkout", "-q", "-b", "issue/4-p")
    wrote = run_hook(
        "pre-tool-use", write_event(main, b / "src.py"), monkeypatch, capsys
    )
    assert wrote == {}
    commit(b, {"src.py": "x\n"})

    answer = run_hook(
        "stop", {"cwd": str(main), "session_id": "s1"}, monkeypatch, capsys
    )
    assert answer["decision"] == "block"
    assert str(b) in answer["reason"]


def test_a_logged_worktree_that_no_longer_exists_is_skipped(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    run_hook("pre-tool-use", write_event(a, b / "src.py"), monkeypatch, capsys)
    git(main, "worktree", "remove", "--force", str(b))
    event = {"cwd": str(a), "session_id": "s1"}
    assert run_hook("stop", event, monkeypatch, capsys) == {}


# --- The write log -----------------------------------------------------------


def test_an_allowed_write_records_its_worktree_as_one_file(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    run_hook("pre-tool-use", write_event(a, b / "src.py"), monkeypatch, capsys)
    run_hook("pre-tool-use", write_event(a, b / "other.py"), monkeypatch, capsys)
    entries = list(sessions_dir(main, "s1").iterdir())
    assert len(entries) == 1
    assert Path(entries[0].read_text(encoding="utf-8").strip()) == b


def test_a_write_into_the_factory_directory_is_not_logged(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    run_hook(
        "pre-tool-use", write_event(a, b / ".factory/2/plan.md"), monkeypatch, capsys
    )
    run_hook("pre-tool-use", write_event(a, b / "src.py"), monkeypatch, capsys)
    assert len(list(sessions_dir(main, "s1").iterdir())) == 1


def test_a_refused_write_is_not_logged(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    bare = main.parent / "bare"
    git(main, "worktree", "add", "-q", "-b", "issue/3-x", str(bare), "dev")
    a = ticket(main, 1)
    event = write_event(a, bare / "src.py")
    answer = run_hook("pre-tool-use", event, monkeypatch, capsys)
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert not sessions_dir(main, "s1").exists()


def test_concurrent_writers_lose_no_entry(main: Path) -> None:
    session = ticket(main, 1)
    targets = [ticket(main, n) for n in range(2, 6)]

    def hammer(target: Path) -> None:
        for _ in range(10):
            worktrees.log_write(session, target / "x.py", "s1")

    threads = [threading.Thread(target=hammer, args=(t,)) for t in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    entries = list(sessions_dir(main, "s1").iterdir())
    assert len(entries) == len(targets)
    found = {Path(e.read_text(encoding="utf-8").strip()) for e in entries}
    assert found == set(targets)


@pytest.mark.parametrize(
    "session_id", ["", "../x", "a/b", "a b", "a.b", "x" * 129, 7, None, ["s1"]]
)
def test_an_invalid_session_id_writes_no_log(
    main: Path,
    session_id: object,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    event = write_event(a, b / "src.py", session_id)
    assert run_hook("pre-tool-use", event, monkeypatch, capsys) == {}
    assert not (main / ".git" / "factory").exists()


def test_a_valid_session_id_does_write_one(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)
    event = write_event(a, b / "src.py", "abc-123_DEF")
    run_hook("pre-tool-use", event, monkeypatch, capsys)
    assert sessions_dir(main, "abc-123_DEF").is_dir()


def test_the_write_log_can_never_change_the_answer(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def explode(*args: object, **kwargs: object) -> None:
        raise RuntimeError("the log is broken")

    a = ticket(main, 1)
    bare = main.parent / "bare"
    git(main, "worktree", "add", "-q", "-b", "issue/3-x", str(bare), "dev")
    b = ticket(main, 2)
    monkeypatch.setattr("factory.cli.log_write", explode)
    monkeypatch.setattr("factory.cli.logged_worktrees", explode)

    denied = run_hook(
        "pre-tool-use", write_event(a, bare / "src.py"), monkeypatch, capsys
    )
    assert denied["hookSpecificOutput"]["permissionDecision"] == "deny"
    allowed = run_hook(
        "pre-tool-use", write_event(a, b / "src.py"), monkeypatch, capsys
    )
    assert allowed == {}

    commit(a, {"src.py": "x\n"})
    stopped = run_hook("stop", {"cwd": str(a), "session_id": "s1"}, monkeypatch, capsys)
    assert stopped["decision"] == "block", "the hook must not fail open"


def test_pre_tool_use_runs_no_subprocess(
    main: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    a, b = ticket(main, 1), ticket(main, 2)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("PreToolUse ran a subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    run_hook("pre-tool-use", write_event(a, b / "src.py"), monkeypatch, capsys)
    assert sessions_dir(main, "s1").is_dir()


@pytest.mark.parametrize("text", ["", "  ", "\n"])
def test_an_empty_log_entry_is_skipped_not_read_as_the_current_directory(
    main: Path, text: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`Path("")` is `.`, which would judge whatever directory the hook runs in."""
    a = ticket(main, 1)
    directory = sessions_dir(main, "s1")
    directory.mkdir(parents=True)
    (directory / "entry").write_text(text, encoding="utf-8")
    monkeypatch.chdir(a)
    assert worktrees.logged_worktrees(main, "s1") == ()


def _git_common(root: Path) -> Path:
    out = git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")
    return Path(out).resolve()


def test_a_separate_git_dir_checkout_is_its_own_repository(tmp_path: Path) -> None:
    """Git writes no `commondir` file there, and the directory is not a worktree's."""
    from factory.chain import common_dir

    work = tmp_path / "work"
    work.mkdir()
    (tmp_path / "elsewhere").mkdir()
    git(work, "init", "-q", "--separate-git-dir", str(tmp_path / "elsewhere" / "g.git"))
    found = common_dir(work)
    assert found is not None
    assert found.resolve() == _git_common(work)


def test_a_submodule_is_its_own_repository_not_its_superproject(
    tmp_path: Path,
) -> None:
    from factory.chain import common_dir

    lib = tmp_path / "lib"
    lib.mkdir()
    git(lib, "init", "-q", "-b", "dev")
    _configure(lib)
    commit(lib, {"l.py": "l\n"})
    sup = tmp_path / "sup"
    sup.mkdir()
    git(sup, "init", "-q", "-b", "dev")
    _configure(sup)
    commit(sup, {"s.py": "s\n"})
    git(
        sup,
        "-c",
        "protocol.file.allow=always",
        "submodule",
        "add",
        "-q",
        str(lib),
        "sub",
    )
    found = common_dir(sup / "sub")
    assert found is not None
    assert found.resolve() == _git_common(sup / "sub")
    assert found.resolve() != common_dir(sup)
