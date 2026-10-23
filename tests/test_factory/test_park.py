"""
`factory park`: a worker hands a ticket back (#219).

Real temporary git repositories with linked worktrees, so "the ticket's own
worktree" is the real thing. Every call goes through `main`, with the session's
directory set by `chdir`, as a worker would run it.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from factory.chain import front_matter, read_chain
from factory.cli import main
from factory.exit_codes import ExitCode

DOCS = Path(__file__).resolve().parents[2] / "docs" / "factory"


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return done.stdout.strip()


def make_repo(base: Path) -> Path:
    """A primary checkout on `dev` with one commit, signing and hooks off."""
    root = (base / "main").resolve()
    root.mkdir()
    git(root, "init", "-q", "-b", "dev")
    hooks = base / "no-hooks"
    hooks.mkdir()
    for key, value in (
        ("user.name", "Test"),
        ("user.email", "test@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", str(hooks)),
    ):
        git(root, "config", key, value)
    (root / "a.py").write_text("a\n", encoding="utf-8")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "c1")
    return root


def add_ticket(main: Path, n: int, slug: str = "x") -> Path:
    """A linked worktree on `issue/<n>-<slug>`."""
    root = main.parent / f"wt{n}"
    git(main, "worktree", "add", "-q", "-b", f"issue/{n}-{slug}", str(root), "dev")
    return root


PROVEN = "---\nticket: 7\nproof:\n  suite: pass\n---\n"
ACCEPTED = "---\nticket: 7\naccepted_by: nassim\n---\n"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


def write_chain(worktree: Path, ticket: int, files: dict[str, str]) -> None:
    root = worktree / ".factory" / str(ticket)
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, dict[str, Any]]:
    code = main(["--json", "park", *argv])
    out = capsys.readouterr().out
    return code, json.loads(out) if out.strip() else {}


def park_file(worktree: Path, ticket: int = 7) -> Path:
    return worktree / ".factory" / str(ticket) / "park.md"


@pytest.fixture
def wt(repo: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ticket 7's worktree, at the design stage, and the session sits in it."""
    worktree = add_ticket(repo, 7)
    write_chain(worktree, 7, {"intent.md": ACCEPTED})
    monkeypatch.chdir(worktree)
    return worktree


def test_reason_writes_a_needs_human_park_in_the_ticket_worktree(
    wt: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = run(capsys, "--reason", "the game must be running")
    assert code == ExitCode.OK
    assert payload["kind"] == "needs-human"
    front = front_matter(park_file(wt))
    assert front["ticket"] == "7"
    assert front["kind"] == "needs-human"
    assert front["stage"] == "design"
    assert front["parked_at"].endswith("Z")
    text = park_file(wt).read_text(encoding="utf-8")
    assert text.split("\n---\n", 1)[1].strip() == "the game must be running"


def test_question_writes_a_spec_gap_park(
    wt: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = run(capsys, "--question", "Which map does criterion 3 mean?")
    assert code == ExitCode.OK
    assert front_matter(park_file(wt))["kind"] == "spec-gap"


def test_read_chain_returns_the_written_front_matter(
    wt: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(capsys, "--reason", "stuck")
    chain = read_chain(wt, 7)
    assert "park.md" in chain.present
    assert set(chain.park) == {"ticket", "kind", "stage", "parked_at"}
    assert chain.park == front_matter(park_file(wt))


@pytest.mark.parametrize(
    ("argv", "complaint"),
    [
        ([], "required"),
        (["--reason", "a", "--question", "b"], "not allowed with"),
        (["--reason"], "expected one argument"),
    ],
)
def test_the_wrong_flags_are_misuse(
    wt: Path,
    argv: list[str],
    complaint: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as caught:
        main(["--json", "park", *argv])
    assert caught.value.code == ExitCode.MISUSE
    assert complaint in capsys.readouterr().err
    assert not park_file(wt).exists()


@pytest.mark.parametrize("flag", ["--reason", "--question"])
@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_an_empty_text_is_misuse_and_writes_nothing(
    wt: Path, flag: str, text: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, payload = run(capsys, flag, text)
    assert code == ExitCode.MISUSE
    assert "error" in payload
    assert not park_file(wt).exists()


def test_no_ticket_on_the_session_branch_is_misuse(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(repo)
    code, _ = run(capsys, "--reason", "x")
    assert code == ExitCode.MISUSE
    assert not (repo / ".factory").exists()


def test_a_ticket_number_from_the_primary_writes_in_that_tickets_worktree(
    repo: Path,
    wt: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(repo)
    code, _ = run(capsys, "7", "--reason", "from outside")
    assert code == ExitCode.OK
    assert park_file(wt).is_file()
    assert not (repo / ".factory").exists()


def test_a_ticket_nobody_is_working_is_misuse(
    repo: Path,
    wt: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(repo)
    code, _ = run(capsys, "9", "--reason", "x")
    assert code == ExitCode.MISUSE


def test_two_worktrees_for_the_ticket_need_a_human(
    repo: Path,
    wt: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    other = repo.parent / "wt7-again"
    git(repo, "worktree", "add", "-q", "-b", "issue/7-y", str(other), "dev")
    monkeypatch.chdir(repo)
    code, _ = run(capsys, "7", "--reason", "x")
    assert code == ExitCode.NEEDS_HUMAN


def test_park_never_writes_state_json(
    wt: Path, repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(capsys, "--reason", "x")
    assert not (repo / ".git" / "factory").exists()


def test_a_second_park_is_needs_human_names_the_kind_and_writes_nothing(
    wt: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    run(capsys, "--question", "first")
    before = park_file(wt).read_text(encoding="utf-8")
    code, payload = run(capsys, "--reason", "second")
    assert code == ExitCode.NEEDS_HUMAN
    assert "spec-gap" in payload["error"]
    assert park_file(wt).read_text(encoding="utf-8") == before


def test_a_blocked_chain_parks_with_a_null_stage(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    worktree = add_ticket(repo, 7)
    #: A plan with no spec: routing calls the chain inconsistent and stops.
    write_chain(worktree, 7, {"intent.md": ACCEPTED, "plan.md": PROVEN})
    monkeypatch.chdir(worktree)
    code, payload = run(capsys, "--reason", "x")
    assert code == ExitCode.OK
    assert payload["stage"] is None
    assert front_matter(park_file(worktree))["stage"] == "null"


def test_a_malformed_verdict_parks_with_a_null_stage(
    repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    worktree = add_ticket(repo, 7)
    write_chain(
        worktree,
        7,
        {
            "intent.md": ACCEPTED,
            "spec.md": "---\nticket: 7\n---\n",
            "spec-review.md": "---\nverdict: pass\n---\n",
            "plan.md": PROVEN,
            "review.md": "---\nverdict: maybe\n---\n",
        },
    )
    monkeypatch.chdir(worktree)
    code, payload = run(capsys, "--reason", "x")
    assert code == ExitCode.OK
    assert payload["stage"] is None
    assert front_matter(park_file(worktree))["stage"] == "null"


def test_the_stage_is_the_one_routing_gives_at_that_moment(
    wt: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_chain(
        wt,
        7,
        {
            "spec.md": "---\nticket: 7\n---\n",
            "spec-review.md": "---\nverdict: pass\n---\n",
            "plan.md": "---\nticket: 7\nproof:\n  suite: null\n---\n",
        },
    )
    code, payload = run(capsys, "--reason", "x")
    assert code == ExitCode.OK
    assert payload["stage"] == "build-implementing"


# --- The documents -----------------------------------------------------------


def _row(path: Path, prefix: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    return next(line for line in lines if line.startswith(prefix))


def test_design_lists_the_park_exit_codes() -> None:
    row = _row(DOCS / "design.md", "| `park ")
    cells = [cell.strip() for cell in row.strip("|").split(" | ")]
    assert "already exists" in cells[-1]
    assert "flag" in cells[-2]


def test_artifacts_md_contracts_park_and_run() -> None:
    text = (DOCS / "artifacts.md").read_text(encoding="utf-8")
    park = text.split("### `park.md` (v2)", 1)[1].split("### `run.md`", 1)[0]
    for field in ("`ticket`", "`parked_at`", "`kind`", "`stage`"):
        assert field in park
    run_section = text.split("### `run.md` (v2)", 1)[1].split("### `qa.md`", 1)[0]
    for field in ("`ticket`", "`stage`", "`attempt`", "`cycles."):
        assert field in run_section
