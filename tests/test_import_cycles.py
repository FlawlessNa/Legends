"""
No import cycle inside a package. A cycle works until the import order changes:
`botting.core`'s `__init__` imports a module that reaches `botting.communications`,
whose parser does `from botting.core import ActionRequest`, and that line only
finds the name because `core` happened to bind it first.

Only imports that run when the module loads count: not those inside a function,
and not those under `if TYPE_CHECKING:`, which exist for the type checker alone.
`from package import name` is an edge to the package's `__init__`, and to
`package.name` when that is a module of ours.

Fix a cycle by importing from the module that defines the name
(`botting.core.action_data`), never by adding an exception.
"""

import ast
from pathlib import Path

import pytest

from tests.test_layering import ROOT, _source_files

PACKAGES = ("botting", "maple", "game_data")


def module_name(file: Path) -> str:
    parts = list(file.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def load_time_imports(
    source: str, package: tuple[str, ...], known: set[str]
) -> set[str]:
    """
    The modules of ours (`known`) that `source` imports as it loads.

    `from package import name` is `package.name` when that is a module, and
    otherwise the package's `__init__`, which `name` is read from.
    """
    tree = ast.parse(source)
    deferred: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda) or (
            isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test)
        ):
            deferred.update(id(inner) for inner in ast.walk(node) if inner is not node)
    found: set[str] = set()
    for node in ast.walk(tree):
        if id(node) in deferred:
            continue
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module.split(".") if node.module else []
            if node.level:
                base = [*package[: len(package) - node.level + 1], *base]
            for alias in node.names:
                submodule = ".".join([*base, alias.name])
                found.add(submodule if submodule in known else ".".join(base))
    return found & known


def import_graph(top: str) -> dict[str, set[str]]:
    files = {module_name(file): file for file in _source_files(top)}
    known = set(files)
    graph: dict[str, set[str]] = {}
    for name, file in files.items():
        parts = tuple(name.split("."))
        package = parts if file.name == "__init__.py" else parts[:-1]
        imports = load_time_imports(file.read_text(encoding="utf-8"), package, known)
        graph[name] = imports - {name}
    return graph


def cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    """The strongly connected components of two or more modules (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []

    def visit(node: str) -> None:
        index[node] = low[node] = len(index)
        stack.append(node)
        on_stack.add(node)
        for target in sorted(graph[node]):
            if target not in index:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], index[target])
        if low[node] == index[node]:
            members = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                members.append(member)
                if member == node:
                    break
            if len(members) > 1:
                found.append(sorted(members))

    for node in sorted(graph):
        if node not in index:
            visit(node)
    return found


@pytest.mark.parametrize("top", PACKAGES)
def test_a_package_has_no_import_cycle(top: str) -> None:
    found = cycles(import_graph(top))

    assert found == [], (
        f"import cycles in {top}/: {found}. Import from the module that defines "
        "the name, not from a package that re-exports it."
    )


def test_a_cycle_through_a_package_init_is_found() -> None:
    graph = {
        "a": {"a.x"},
        "a.x": {"b"},
        "b": {"b.y"},
        "b.y": {"a"},
    }

    assert cycles(graph) == [["a", "a.x", "b", "b.y"]]
    assert cycles({"a": {"a.x"}, "a.x": set()}) == []


def test_imports_that_do_not_run_at_load_are_not_edges() -> None:
    source = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    from botting.core import Bot\ndef later():\n    from botting.communications import Parser\nfrom botting.core import ActionRequest\nfrom . import sibling"
    known = {"botting.core", "botting.communications", "botting.x.sibling"}

    found = load_time_imports(source, ("botting", "x"), known)

    assert found == {"botting.core", "botting.x.sibling"}
