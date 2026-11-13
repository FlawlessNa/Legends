"""
The paths the docs name exist. `AGENTS.md` files and `docs/` are what an agent
trusts to find its way, and a path that moved or never existed sends it hunting.

A backticked token that starts with one of the repo's top-level directories,
such as `maple/screen/` or `tests/frames/v1.json`, must resolve to a file or
directory. Skipped: paths git ignores (`data/`, `.venv/`: they exist on a
machine, not in a clone), paths with a placeholder or wildcard (`<id>`, `*`),
and the few historical mentions in `HISTORICAL`.

A dead path is fixed in the doc. `HISTORICAL` is for a mention that is meant to
name something that no longer exists, such as a file an ADR records as removed.
"""

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DOC_ROOTS = ("docs",)
DOC_NAMES = ("AGENTS.md",)

# (doc relative to ROOT, the path as written) -> why the path is meant to be dead.
HISTORICAL: dict[tuple[str, str], str] = {
    ("botting/AGENTS.md", "botting/visuals/object_detection.py"): "removed by #85",
    ("docs/ARCHITECTURE.md", "botting/visuals/object_detection.py"): "removed by #85",
    (
        "docs/adr/0004-virtual-coordinates-and-map-from-game-data.md",
        "toolkit/create_map.py",
    ): "removed by #399",
}

BACKTICKED = re.compile(r"`([^`\n]+)`")
PLACEHOLDER = re.compile(r"[<>*{}$]|\.\.\.")
TRAILER = re.compile(r"(::.*|:\d+([,-]\d+)*)$")


def docs() -> list[Path]:
    found = [p for name in DOC_NAMES for p in ROOT.rglob(name)]
    found += [p for d in DOC_ROOTS for p in (ROOT / d).rglob("*.md")]
    return sorted(
        p
        for p in set(found)
        if not any(part.startswith(".") or part == "node_modules" for part in p.parts)
    )


def top_level_directories() -> set[str]:
    return {p.name for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith(".")}


def named_paths(doc: Path, tops: set[str]) -> list[str]:
    """The backticked paths in `doc` that start with a top-level directory."""
    paths = []
    for token in BACKTICKED.findall(doc.read_text(encoding="utf-8")):
        token = TRAILER.sub("", token.strip())
        if " " in token or PLACEHOLDER.search(token):
            continue
        if token.split("/", 1)[0] in tops and "/" in token:
            paths.append(token)
    return paths


def ignored(paths: list[str]) -> set[str]:
    """Which of `paths` git ignores. Empty when git can't say (no repository)."""
    if not paths:
        return set()
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-z", "--stdin"],
            input="\0".join(paths).encode(),
            capture_output=True,
            cwd=ROOT,
            check=False,
            timeout=30,
        )
    except OSError, subprocess.TimeoutExpired:
        return set()
    return set(result.stdout.decode().split("\0")) - {""}


def exists(path: str) -> bool:
    """The path exists, or is `module.name` for a Python module that does."""
    if (ROOT / path).exists():
        return True
    module, _, name = path.rpartition(".")
    return bool(name.isidentifier() and (ROOT / f"{module}.py").is_file())


def dead_paths() -> list[str]:
    tops = top_level_directories()
    named = {(doc, path) for doc in docs() for path in named_paths(doc, tops)}
    skipped = ignored(sorted({path for _, path in named}))
    return sorted(
        f"{doc.relative_to(ROOT).as_posix()}: `{path}`"
        for doc, path in named
        if path not in skipped
        and (doc.relative_to(ROOT).as_posix(), path) not in HISTORICAL
        and not exists(path)
    )


def test_every_path_the_docs_name_exists() -> None:
    dead = dead_paths()

    assert not dead, "dead paths in the docs:\n" + "\n".join(dead)


def test_the_check_finds_a_dead_path(tmp_path: Path) -> None:
    doc = tmp_path / "AGENTS.md"
    doc.write_text("See `maple/no_such_module.py` and `maple/AGENTS.md`.\n")

    named = named_paths(doc, {"maple"})

    assert named == ["maple/no_such_module.py", "maple/AGENTS.md"]
    assert [p for p in named if not (ROOT / p).exists()] == ["maple/no_such_module.py"]


@pytest.mark.parametrize(
    "token",
    ["maple/screen/<name>.py", "tests/**/*.py", "maple/x.py::test_a", "pytest -m live"],
)
def test_placeholders_and_commands_are_not_paths(token: str, tmp_path: Path) -> None:
    doc = tmp_path / "AGENTS.md"
    doc.write_text(f"`{token}`\n")

    assert [p for p in named_paths(doc, {"maple", "tests"}) if "no_such" in p] == []
    assert "<name>" not in "".join(named_paths(doc, {"maple", "tests"}))
