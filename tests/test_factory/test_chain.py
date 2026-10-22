"""
Chain v2: lists, the loop's artifacts, the version marker, content ids, radii.

The reader is what routing, the hooks and the factory loop all stand on, and it
was blind to lists: every real `spec.md` writes `criteria` as one and every real
`plan.md` writes `radius` as one. The last test here reads the repo's own
committed chains, so a fixture cannot hide that again.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from factory.chain import (
    ARTIFACTS,
    LOOP_ARTIFACTS,
    UnknownChainVersion,
    blob,
    front_matter,
    front_matter_lists,
    radius_errors,
    read_chain,
)
from factory.routing import resolve

TICKET = 7

#: Every chain committed when chain v2 was written (`9654223`). Pinned by number
#: so a later `chain: 2` ticket cannot change what this test asserts about v1.
COMMITTED_V1 = (140, 153, 162, 179, 189, 191, 194, 197, 199, 202, 206, 209, 214)

REPO = Path(__file__).resolve().parents[2]


def _lists(text: str, tmp_path: Path) -> dict[str, tuple[str, ...]]:
    path = tmp_path / "artifact.md"
    path.write_text(text, encoding="utf-8")
    return front_matter_lists(path)


def _chain(tmp_path: Path, **files: str) -> Path:
    root = tmp_path / ".factory" / str(TICKET)
    root.mkdir(parents=True, exist_ok=True)
    for name, text in files.items():
        (root / name.replace("_", "-").replace("-md", ".md")).write_text(
            text, encoding="utf-8"
        )
    return tmp_path


# --- Lists ------------------------------------------------------------------


def test_a_block_list_reads_in_order(tmp_path: Path) -> None:
    found = _lists("---\ncriteria:\n  - first\n  - second\n---\n", tmp_path)
    assert found["criteria"] == ("first", "second")


def test_items_keep_their_quotes(tmp_path: Path) -> None:
    found = _lists('---\nradius:\n  - "a b"\n  - plain \n---\n', tmp_path)
    assert found["radius"] == ('"a b"', "plain")


def test_a_list_ends_at_the_next_top_level_key(tmp_path: Path) -> None:
    found = _lists(
        "---\nradius:\n  - a.py\ntasks: null\nproof:\n  suite: pass\n---\n", tmp_path
    )
    assert found["radius"] == ("a.py",)
    assert "proof" not in found


def test_blank_lines_and_comments_inside_a_list_are_skipped(tmp_path: Path) -> None:
    found = _lists("---\nradius:\n  - a.py\n\n  # why\n  - b.py\n---\n", tmp_path)
    assert found["radius"] == ("a.py", "b.py")


def test_flow_lists(tmp_path: Path) -> None:
    found = _lists("---\ndocs_cleared: []\nradius: [a.py, b/**]\n---\n", tmp_path)
    assert found["docs_cleared"] == ()
    assert found["radius"] == ("a.py", "b/**")


def test_a_mapping_item_makes_the_key_unreadable(tmp_path: Path) -> None:
    """Half-reading a list of mappings is worse than not reading it."""
    found = _lists(
        "---\ntasks:\n  - id: one\n    radius: a.py\nradius:\n  - a.py\n---\n",
        tmp_path,
    )
    assert "tasks" not in found
    assert found["radius"] == ("a.py",)


def test_a_bare_mapping_item_with_no_value_is_a_mapping(tmp_path: Path) -> None:
    assert "tasks" not in _lists("---\ntasks:\n  - id:\n---\n", tmp_path)


def test_prose_with_a_colon_is_not_a_mapping(tmp_path: Path) -> None:
    """Real criteria say things like 'the answer: a stage'. They must be read."""
    found = _lists(
        "---\ncriteria:\n  - the answer names three things: stage, role\n"
        "  - plain one\n---\n",
        tmp_path,
    )
    assert found["criteria"] == (
        "the answer names three things: stage, role",
        "plain one",
    )


def test_items_at_differing_indentation_make_the_key_unreadable(
    tmp_path: Path,
) -> None:
    found = _lists("---\nradius:\n  - a.py\n    - b.py\n---\n", tmp_path)
    assert "radius" not in found


def test_scalars_are_not_lists(tmp_path: Path) -> None:
    found = _lists("---\nticket: 7\nmethod: suite\n---\n", tmp_path)
    assert found == {}


def test_front_matter_still_ignores_lists(tmp_path: Path) -> None:
    """The scalar reader is untouched: lists come only through the new function."""
    path = tmp_path / "plan.md"
    path.write_text("---\nticket: 7\nradius:\n  - a.py\n---\n", encoding="utf-8")
    assert front_matter(path) == {"ticket": "7", "radius": ""}


# --- The chain --------------------------------------------------------------


def test_the_loop_s_artifacts_are_read(tmp_path: Path) -> None:
    root = _chain(
        tmp_path,
        spec_review_md="---\nverdict: pass\n---\n",
        acceptance_md="---\naccepted_by: nassim\n---\n",
        proof_md="---\nsuite: pass\n---\n",
        answers_md="---\nticket: 7\n---\n",
        park_md="---\nkind: spec-gap\n---\n",
    )
    chain = read_chain(root, TICKET)
    assert chain.spec_review["verdict"] == "pass"
    assert chain.acceptance["accepted_by"] == "nassim"
    assert chain.proof["suite"] == "pass"
    assert chain.answers["ticket"] == "7"
    assert chain.park["kind"] == "spec-gap"
    assert {"acceptance.md", "proof.md", "park.md"} <= chain.present


def test_criteria_and_radius_are_tuples(tmp_path: Path) -> None:
    root = _chain(
        tmp_path,
        spec_md="---\ncriteria:\n  - one\n  - two\n---\n",
        plan_md="---\nradius:\n  - factory/**\n---\n",
    )
    chain = read_chain(root, TICKET)
    assert chain.criteria == ("one", "two")
    assert chain.radius == ("factory/**",)


def test_absent_or_unreadable_lists_are_empty(tmp_path: Path) -> None:
    root = _chain(tmp_path, plan_md="---\nradius:\n  - id: x\n---\n")
    chain = read_chain(root, TICKET)
    assert chain.criteria == ()
    assert chain.radius == ()


def test_artifacts_keeps_its_six_names() -> None:
    """`session_report` prints one line per name; a v1 session must not see v2 files."""
    assert ARTIFACTS == (
        "intent.md",
        "spec.md",
        "spec-review.md",
        "plan.md",
        "qa.md",
        "review.md",
    )
    assert LOOP_ARTIFACTS == (
        "acceptance.md",
        "proof.md",
        "answers.md",
        "park.md",
        "run.md",
    )


# --- Version ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("intent", "version"),
    [
        (None, 1),
        ("---\nticket: 7\n---\n", 1),
        ("---\nchain: 1\n---\n", 1),
        ("---\nchain: 2\n---\n", 2),
    ],
)
def test_the_version_marker(tmp_path: Path, intent: str | None, version: int) -> None:
    root = _chain(tmp_path) if intent is None else _chain(tmp_path, intent_md=intent)
    assert read_chain(root, TICKET).version == version


@pytest.mark.parametrize("value", ["3", "two", "2  # a comment", "", "null"])
def test_an_unknown_version_is_an_error_not_a_guess(tmp_path: Path, value: str) -> None:
    root = _chain(tmp_path, intent_md=f"---\nchain: {value}\n---\n")
    with pytest.raises(UnknownChainVersion):
        _ = read_chain(root, TICKET).version


# --- blob -------------------------------------------------------------------

git = shutil.which("git")
needs_git = pytest.mark.skipif(git is None, reason="no git on PATH")


def _git(repo: Path, *args: str) -> str:
    assert git is not None
    done = subprocess.run(
        [git, "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture
def crlf_repo(tmp_path: Path) -> Path:
    """A repo with `core.autocrlf=true`, one LF file committed, CRLF on disk."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    for key, value in (
        ("user.name", "test"),
        ("user.email", "test@example.invalid"),
        ("core.hooksPath", ""),
        ("core.autocrlf", "true"),
    ):
        _git(repo, "config", key, value)
    (repo / "docs").mkdir()
    (repo / "docs" / "spec.md").write_bytes(b"line one\nline two\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "one")
    (repo / "docs" / "spec.md").unlink()
    _git(repo, "checkout", "--", "docs/spec.md")
    return repo


@needs_git
def test_blob_is_the_content_id_whatever_the_line_endings_on_disk(
    crlf_repo: Path,
) -> None:
    on_disk = (crlf_repo / "docs" / "spec.md").read_bytes()
    assert b"\r\n" in on_disk, "the fixture must reproduce autocrlf's checkout"
    lf = crlf_repo / "lf.txt"
    lf.write_bytes(b"line one\nline two\n")
    expected = _git(crlf_repo, "hash-object", str(lf))
    assert blob(crlf_repo, "HEAD", "docs/spec.md") == expected


@needs_git
@pytest.mark.parametrize(
    ("commit", "relpath"),
    [("HEAD", "docs/missing.md"), ("HEAD", "docs"), ("0" * 40, "docs/spec.md")],
)
def test_blob_is_none_for_what_is_not_a_file_at_that_commit(
    crlf_repo: Path, commit: str, relpath: str
) -> None:
    assert blob(crlf_repo, commit, relpath) is None


def test_blob_is_none_when_git_cannot_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(*_: object, **__: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr("factory.chain.subprocess.run", missing)
    assert blob(tmp_path, "HEAD", "x.md") is None


# --- Radius -----------------------------------------------------------------


@pytest.mark.parametrize(
    "entry",
    [
        "factory/chain.py",
        "factory/**",
        ".claude/skills/factory/**",
        ".factory/139/**",
        "AGENTS.md",
        ".gitignore",
    ],
)
def test_a_valid_radius_entry(entry: str) -> None:
    assert radius_errors((entry,)) == ()


@pytest.mark.parametrize(
    "entry",
    [
        "factory/*.py",
        "factory/**/x.py",
        "**",
        "/abs/path.py",
        "C:/x.py",
        "factory\\chain.py",
        "factory/",
        "factory//x.py",
        "./x.py",
        "../x.py",
        "a/../b.py",
        "a/?.py",
        "a/[ab].py",
        "",
    ],
)
def test_an_invalid_radius_entry_is_named_with_the_allowed_forms(entry: str) -> None:
    errors = radius_errors((entry,))
    assert len(errors) == 1
    assert repr(entry) in errors[0]
    assert "path/to/file" in errors[0]
    assert "path/to/dir/**" in errors[0]


def test_only_bad_entries_are_reported() -> None:
    assert len(radius_errors(("ok.py", "bad/*.py", "dir/**", "**"))) == 2


# --- The repo's own chains --------------------------------------------------


def _raw_list_lines(path: Path, key: str) -> int:
    """`- ` lines under `key:` in the raw text, counted independently of the reader."""
    lines = path.read_text(encoding="utf-8").splitlines()
    count, inside = 0, False
    for line in lines[1:]:
        if line.startswith("---"):
            break
        if line.startswith(f"{key}:"):
            inside = True
            continue
        if inside and line[:1] not in {" ", "\t", ""}:
            break
        if inside and line.lstrip().startswith("- "):
            count += 1
    return count


@pytest.mark.parametrize("ticket", COMMITTED_V1)
def test_the_repo_s_committed_chains_read_cleanly(ticket: int) -> None:
    root = REPO / ".factory" / str(ticket)
    if not root.is_dir():  # pragma: no cover - the chains are committed
        pytest.skip(f"no committed chain for #{ticket}")
    chain = read_chain(REPO, ticket)

    spec = root / "spec.md"
    if spec.is_file() and _raw_list_lines(spec, "criteria"):
        assert len(chain.criteria) == _raw_list_lines(spec, "criteria")

    if (root / "plan.md").is_file():
        assert chain.radius, f"#{ticket}'s plan.md radius did not read"
        assert radius_errors(chain.radius) == ()

    assert chain.version == 1
    resolve(REPO, f"issue/{ticket}-x")
