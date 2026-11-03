"""
`game_data` starts fast and stays layered.

Importing `maple` loads the detection stack (169 s cold, measured 2026-10-26),
so `game_data` imports neither `maple` nor `botting`, nor `torch` or
`ultralytics`. `cv2` is allowed only in `render/`, and `scenes/`, which
draws through it. The layers import only the layers to their left:

    archive/ <- extraction/ <- catalogue/ <- report/, render/ <- scenes/

Nothing in `game_data` imports `ml_training`, which builds on `scenes/`.

Layers that don't exist yet are skipped, and pass once they arrive.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from tests.test_game_data.wz_writer import Img, Int, write_tree

PACKAGE = Path(__file__).resolve().parents[2] / "game_data"
LAYERS = [
    "archive",
    "extraction",
    "catalogue",
    "sprites",
    "report",
    "render",
    "scenes",
]

# What each layer may import from the others. `report/` and `render/` both sit
# on the catalogue, and not on each other.
ALLOWED = {
    "archive": set[str](),
    "extraction": {"archive"},
    "catalogue": {"archive", "extraction"},
    "sprites": {"archive", "extraction", "catalogue"},
    "report": {"archive", "extraction", "catalogue"},
    "render": {"archive", "extraction", "catalogue"},
    "scenes": {"archive", "extraction", "catalogue", "render"},
}

# Above `game_data`, none of which a layer may import.
OUTSIDE = ["maple", "botting", "ml_training"]

FORBIDDEN = ["maple", "botting", "torch", "ultralytics", "cv2"]


def _modules() -> list[str]:
    """
    `game_data` and every module in its existing layers, `render/` and
    `scenes/` excepted: they import `cv2`.
    """
    modules = ["game_data", "game_data.config", "game_data.cli"]
    for layer in LAYERS:
        folder = PACKAGE / layer
        if layer in ("render", "scenes") or not folder.is_dir():
            continue
        for file in sorted(folder.rglob("*.py")):
            parts = file.relative_to(PACKAGE.parent).with_suffix("").parts
            if parts[-1] == "__init__":
                parts = parts[:-1]
            modules.append(".".join(parts))
    return modules


def test_importing_game_data_loads_neither_the_bot_nor_its_detection_stack() -> None:
    modules = _modules()
    assert "game_data.archive" in modules
    code = "\n".join(
        [
            "import importlib, sys",
            f"sys.path.insert(0, {str(PACKAGE.parent)!r})",
            f"for name in {modules!r}:",
            "    importlib.import_module(name)",
            f"print(sorted(m for m in {FORBIDDEN!r} if m in sys.modules))",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_python_m_game_data_status_loads_neither_the_bot_nor_its_detection_stack(
    tmp_path: Path,
) -> None:
    """`status` runs at bot startup, so its whole path is held to the guard."""
    data = tmp_path / "Data"
    write_tree(data / "Etc", [Img("1.img", [Int("a", 1)])], ini=False)
    argv = ["game_data", "status", "--client", str(data), "--root", str(tmp_path)]
    code = "\n".join(
        [
            "import runpy, sys",
            f"sys.path.insert(0, {str(PACKAGE.parent)!r})",
            f"sys.argv = {argv!r}",
            "try:",
            "    runpy.run_module('game_data', run_name='__main__', alter_sys=True)",
            "except SystemExit as exit:",
            "    assert exit.code == 0, exit.code",
            f"print(sorted(m for m in {FORBIDDEN!r} if m in sys.modules))",
        ]
    )

    result = subprocess.run(
        [sys.executable, "-I", "-c", code],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        f"missing: {tmp_path} has no extraction; run `python -m game_data extract`",
        "[]",
    ]


def _imported_layers(source: str, package: tuple[str, ...]) -> set[str]:
    """
    The other `game_data` layers a module imports, absolutely or relatively.

    :param package: The module's package, such as `("game_data", "archive")`.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        names: list[tuple[str, ...]] = []
        if isinstance(node, ast.Import):
            names = [tuple(alias.name.split(".")) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = tuple(node.module.split(".")) if node.module else ()
            if node.level:
                base = package[: len(package) - node.level + 1] + base
            names = [base]
            if len(base) == 1 and base[0] == "game_data":
                names = [(*base, alias.name) for alias in node.names]
        for name in names:
            if len(name) >= 2 and name[0] == "game_data" and name[1] in LAYERS:
                found.add(name[1])
    found.discard(package[1])
    return found


@pytest.mark.parametrize("layer", LAYERS)
def test_a_layer_imports_only_the_layers_to_its_left(layer: str) -> None:
    folder = PACKAGE / layer
    if not folder.is_dir():
        pytest.skip(f"game_data/{layer}/ doesn't exist yet")
    offences: dict[str, list[str]] = {}
    for file in sorted(folder.rglob("*.py")):
        package = file.relative_to(PACKAGE.parent).parent.parts
        imported = _imported_layers(file.read_text(encoding="utf-8"), package)
        if bad := imported - ALLOWED[layer]:
            offences[str(file.relative_to(PACKAGE))] = sorted(bad)

    assert offences == {}


def test_the_layering_check_sees_relative_and_absolute_imports() -> None:
    source = (
        "from ...catalogue import x\n"
        "from ..catalogue import inside_archive\n"
        "import game_data.report.page\n"
        "from game_data import render, config\n"
        "from . import nodes\n"
        "from .nodes import Node\n"
        "def lazy():\n"
        "    from ...extraction import y\n"
    )

    found = _imported_layers(source, ("game_data", "archive", "inner"))

    assert found == {"catalogue", "report", "render", "extraction"}


def _imported_roots(source: str) -> set[str]:
    """The top-level packages a module imports absolutely."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module.split(".")[0])
    return found


def test_no_module_of_game_data_imports_the_bot_or_ml_training() -> None:
    offences = {
        str(file.relative_to(PACKAGE)): sorted(bad)
        for file in sorted(PACKAGE.rglob("*.py"))
        if (bad := _imported_roots(file.read_text(encoding="utf-8")) & set(OUTSIDE))
    }

    assert offences == {}


def test_the_outside_check_sees_imports_of_each_form() -> None:
    source = "import maple.x\nfrom ml_training import y\ndef f():\n    import botting\n"

    assert _imported_roots(source) >= set(OUTSIDE)
