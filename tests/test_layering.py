"""
The repo's import direction, as `AGENTS.md` ("The repo") states it.

- `maple` imports `botting`, never the reverse: nothing in `botting/` imports
  `maple`.
- `game_data` imports neither `maple` nor `botting`.
- `toolkit/` is imported by nothing outside `toolkit/` and `tests/`: production
  code never depends on a standalone script, but the tests of a toolkit tool
  must be able to import it.

Every import statement counts, wherever it sits: at module level, inside a
function, or under `if TYPE_CHECKING:`. So does `importlib.import_module` with a
literal name. A name built at run time is not seen.

`game_data`'s own layering, and the proof that importing it stays fast, live in
`tests/test_game_data/test_imports.py`.

A broken rule is fixed, not added to `KNOWN_EXCEPTIONS`. An exception is for an
import that was already there when the rule was written, with an issue that
removes it; the test fails once that import is gone, so the list only shrinks.
"""

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

# Directories that hold no source of ours. Anything starting with "." is
# skipped as well (`.venv`, `.git`, ...).
NOT_SOURCE = {"__pycache__", "data", "node_modules", "build", "dist"}


@dataclass(frozen=True)
class Contract:
    """Modules under `source` may not import the top-level packages `forbidden`."""

    name: str
    source: str  # a top-level directory, or "*" for every one but `forbidden`
    forbidden: frozenset[str]
    exempt: frozenset[str] = frozenset()  # top-level directories the rule skips


CONTRACTS = [
    Contract("botting never imports maple", "botting", frozenset({"maple"})),
    Contract(
        "game_data imports neither maple nor botting",
        "game_data",
        frozenset({"maple", "botting"}),
    ),
    Contract(
        "toolkit is imported by nothing outside toolkit and tests",
        "*",
        frozenset({"toolkit"}),
        exempt=frozenset({"tests"}),
    ),
]

# (file relative to ROOT, the module it imports) -> the issue that removes it.
KNOWN_EXCEPTIONS: dict[tuple[str, str], str] = {
    # The GUI map editor draws its key timeline with the toolkit's visualiser.
    (
        "maple/model/mechanics/minimap_creation/map_editor.py",
        "toolkit.movement_timeline",
    ): "#383",
}


def imported_modules(source: str, package: tuple[str, ...]) -> set[str]:
    """
    Every module a file imports, as an absolute dotted name.

    :param package: The file's package, such as `("botting", "core")`, which
        resolves its relative imports.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module.split(".") if node.module else []
            if node.level:
                base = [*package[: len(package) - node.level + 1], *base]
            if base:
                found.add(".".join(base))
        elif (
            isinstance(node, ast.Call)
            and _is_import_module(node.func)
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return found


def _is_import_module(func: ast.expr) -> bool:
    """`importlib.import_module`, `import_module` or `__import__`."""
    if isinstance(func, ast.Attribute):
        return func.attr == "import_module"
    return isinstance(func, ast.Name) and func.id in {"import_module", "__import__"}


def _source_files(top: str) -> list[Path]:
    """Our Python files under the top-level directory `top`, or "*" for all."""
    if top != "*":
        return sorted((ROOT / top).rglob("*.py"))
    files = sorted(ROOT.glob("*.py"))
    for folder in sorted(ROOT.iterdir()):
        if (
            folder.is_dir()
            and not folder.name.startswith(".")
            and folder.name not in NOT_SOURCE
        ):
            files.extend(
                file
                for file in sorted(folder.rglob("*.py"))
                if not NOT_SOURCE & set(file.relative_to(ROOT).parts)
            )
    return files


def violations(contract: Contract) -> set[tuple[str, str]]:
    """Each `(file, module)` that breaks `contract`, exceptions included."""
    found: set[tuple[str, str]] = set()
    for file in _source_files(contract.source):
        relative = file.relative_to(ROOT)
        found |= file_violations(relative, file.read_text(encoding="utf-8"), contract)
    return found


def file_violations(
    relative: Path, source: str, contract: Contract
) -> set[tuple[str, str]]:
    """Each `(file, module)` in one file, given as a path relative to `ROOT`."""
    if relative.parts[0] in contract.forbidden | contract.exempt:
        return set()  # a package may import itself; an exempt one may import it
    return {
        (relative.as_posix(), module)
        for module in imported_modules(source, relative.parent.parts)
        if module.split(".")[0] in contract.forbidden
    }


@pytest.mark.parametrize("contract", CONTRACTS, ids=lambda c: c.name)
def test_imports_follow_the_layer_rules(contract: Contract) -> None:
    new = violations(contract) - KNOWN_EXCEPTIONS.keys()

    assert new == set(), (
        f"{contract.name}: see AGENTS.md, 'The repo'. Move the code to the "
        "layer that may own it rather than adding an exception."
    )


def test_every_known_exception_still_exists() -> None:
    """An exception whose import is gone is deleted, so the list only shrinks."""
    current = set().union(*(violations(contract) for contract in CONTRACTS))

    assert set(KNOWN_EXCEPTIONS) - current == set()


def test_the_scan_sees_every_form_of_import() -> None:
    source = (
        "import maple.x\n"
        "from botting.core import y\n"
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from toolkit import z\n"
        "def lazy():\n"
        "    import importlib\n"
        "    importlib.import_module('ml_training.a')\n"
        "    __import__('scripts')\n"
        "from ..sibling import w\n"
        "from . import v\n"
    )

    found = imported_modules(source, ("game_data", "archive", "inner"))

    assert found >= {
        "maple.x",
        "botting.core",
        "toolkit",
        "ml_training.a",
        "scripts",
        "game_data.archive.sibling",
        "game_data.archive.inner",
    }


def test_the_scan_covers_every_top_level_package() -> None:
    tops = {file.relative_to(ROOT).parts[0] for file in _source_files("*")}

    assert tops >= {"botting", "maple", "game_data", "tests", "ml_training", "scripts"}


def test_only_toolkit_and_tests_may_import_toolkit() -> None:
    contract = next(c for c in CONTRACTS if c.forbidden == {"toolkit"})
    source = "from toolkit import harvest_glyphs\n"

    assert file_violations(Path("maple/x.py"), source, contract) == {
        ("maple/x.py", "toolkit")
    }
    assert file_violations(Path("botting/x.py"), source, contract) != set()
    assert file_violations(Path("tests/test_x.py"), source, contract) == set()
    assert file_violations(Path("toolkit/y.py"), source, contract) == set()
