"""
Tesseract is set up where it is used, on first use (#302, acceptance criterion
10): importing `botting` or the screen readers doesn't import `pytesseract`,
and no module under `botting/` or `maple/` imports it at module level.
`botting/visuals/in_game_visuals.py` imports it, and sets its executable, the
first time it reads text.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_importing_botting_and_the_screen_readers_does_not_import_pytesseract() -> None:
    readers = sorted(
        f"maple.screen.{path.stem}"
        for path in (ROOT / "maple" / "screen").glob("*.py")
        if path.stem != "__init__"
    )
    code = (
        "import sys, botting, maple.screen, "
        + ", ".join(readers)
        + "; print('pytesseract' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=True,
    )

    assert result.stdout.strip() == "False", result.stderr


def _module_level_imports(tree: ast.Module) -> set[str]:
    """Modules imported outside any function body."""
    found: set[str] = set()
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            found.add(node.module)
        pending.extend(ast.iter_child_nodes(node))
    return found


@pytest.mark.parametrize("package", ["botting", "maple"])
def test_no_module_imports_pytesseract_at_module_level(package: str) -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / package).rglob("*.py"))
        if any(
            name.split(".")[0] == "pytesseract"
            for name in _module_level_imports(
                ast.parse(path.read_text(encoding="utf-8"))
            )
        )
    ]

    assert offenders == []


def test_the_first_ocr_sets_tesseracts_executable() -> None:
    from botting.visuals import in_game_visuals
    from paths import TESSERACT

    pytesseract = in_game_visuals._tesseract()  # pyright: ignore[reportPrivateUsage]

    assert pytesseract.pytesseract.tesseract_cmd == TESSERACT
    assert in_game_visuals._tesseract() is pytesseract  # pyright: ignore[reportPrivateUsage]
