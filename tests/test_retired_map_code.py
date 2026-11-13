"""
The hand-made map files and the grid code are retired (#399, #302 Part 2
acceptance criterion 8): nothing imports them, and no production code reads
`configs/maps/`.

The map comes from the game files through `game_data` (`WorldMap`), and paths
are planned on its `FootholdGraph` (ADR 0004). `configs/maps/Line1Area1.json`
may still sit in the repo until the maintainer's profile no longer names it,
but nothing loads it.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

#: Every package with Python in it, tests included.
SCANNED = (
    "botting",
    "maple",
    "game_data",
    "toolkit",
    "ml_training",
    "scripts",
    "tests",
)

#: The packages a bot runs, or a person runs by hand, which must not read the
#: map files.
PRODUCTION = ("botting", "maple", "game_data", "toolkit", "ml_training", "scripts")

RETIRED_MODULES = (
    "maple.model.mechanics.maple_map",
    "maple.model.mechanics.minimap_creation",
)

RETIRED_NAMES = frozenset(
    {
        "MapleMap",
        "MapleMinimap",
        "MinimapEditsManager",
        "MinimapGrid",
        "MinimapPhysics",
    }
)

RETIRED_PATHS = (
    "maple/model/mechanics/maple_map.py",
    "maple/model/mechanics/minimap_creation",
    "toolkit/create_map.py",
)


def python_files(packages: tuple[str, ...]) -> Iterator[Path]:
    for package in packages:
        yield from (ROOT / package).rglob("*.py")


def is_retired(module: str) -> bool:
    return any(module == m or module.startswith(m + ".") for m in RETIRED_MODULES)


def retired_imports(tree: ast.AST) -> list[str]:
    """Each import, in `tree`, of a retired module or of a retired name."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if is_retired(a.name)]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            names = {a.name for a in node.names}
            if is_retired(module) or names & RETIRED_NAMES:
                found.append(f"from {module} import {', '.join(sorted(names))}")
            else:
                found += [f"{module}.{n}" for n in names if is_retired(f"{module}.{n}")]
    return found


def map_file_paths(tree: ast.AST) -> list[str]:
    """String constants naming `configs/maps`, docstrings aside."""
    docstrings = {
        id(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and "configs/maps" in node.value.replace("\\", "/")
    ]


@pytest.mark.parametrize("path", RETIRED_PATHS)
def test_the_retired_module_is_gone(path: str) -> None:
    assert not (ROOT / path).exists()


def test_no_module_imports_the_map_files_or_grid_code() -> None:
    offenders = {
        str(path.relative_to(ROOT)): found
        for path in python_files(SCANNED)
        if (found := retired_imports(ast.parse(path.read_text(encoding="utf-8"))))
    }

    assert offenders == {}


def test_no_production_code_reads_configs_maps() -> None:
    offenders = {
        str(path.relative_to(ROOT)): found
        for path in python_files(PRODUCTION)
        if (found := map_file_paths(ast.parse(path.read_text(encoding="utf-8"))))
    }

    assert offenders == {}


def test_the_scan_sees_each_form_of_import_and_path() -> None:
    tree = ast.parse(
        "import maple.model.mechanics.maple_map\n"
        "from maple.model.mechanics.minimap_creation.minimap_grid import X\n"
        "from maple.model.mechanics import minimap_creation\n"
        "from somewhere import MinimapGrid\n"
        "from maple.model.mechanics import MovementHandler\n"
        "'''configs/maps in a docstring is fine'''\n"
        "PATH = 'configs\\\\maps\\\\Line1Area1.json'\n"
    )

    assert retired_imports(tree) == [
        "maple.model.mechanics.maple_map",
        "from maple.model.mechanics.minimap_creation.minimap_grid import X",
        "maple.model.mechanics.minimap_creation",
        "from somewhere import MinimapGrid",
    ]
    assert map_file_paths(tree) == ["configs\\maps\\Line1Area1.json"]
