"""
Exhaustive sweep and golden regeneration for the movement lab.

    python toolkit/movement_lab_sweep.py                    # sweep: every Invariant
                                                              # over the whole Corpus,
                                                              # pass/fail per map
    python toolkit/movement_lab_sweep.py --golden <case>     # regenerate one golden
    python toolkit/movement_lab_sweep.py --all-goldens       # regenerate every golden
    python toolkit/movement_lab_sweep.py --check-goldens     # report drift, write nothing

The sweep runs `test_invariants.py` itself (pytest, in-process) and summarizes its
own results per check per map - this script reports over the suite's results, it does
not re-implement them; `test_invariants.py` stays the one source of truth for what
holds. Golden regeneration writes what `test_goldens.py` then reads back - run it only
once a change to the compiled shape is known to be deliberate, never to chase a
failing check into passing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

# Running a script by path puts `toolkit/` on `sys.path`, not the repo root - the root
# goes on explicitly, matching `generate_movement_lab_pairs.py`'s own fix for the same
# problem, so `tests` and `maple` are importable at all.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_maple.movement_lab.test_goldens import (
    CASES,
    GOLDENS_ROOT,
    _deterministic_rendering,
)

_INVARIANTS_MODULE = str(
    Path(__file__).resolve().parent.parent
    / "tests"
    / "test_maple"
    / "movement_lab"
    / "test_invariants.py"
)


class _ResultCollector:
    """A minimal pytest plugin: one outcome per test id, keyed the way pytest itself
    reports it, so a `setup` error (a fixture failing to build the Corpus) is not
    silently dropped in favour of a `call` outcome that never ran."""

    def __init__(self) -> None:
        self.outcomes: dict[str, str] = {}

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call" or report.outcome != "passed":
            self.outcomes[report.nodeid] = report.outcome


def _sweep() -> int:
    collector = _ResultCollector()
    pytest.main(["-q", "--tb=no", _INVARIANTS_MODULE], plugins=[collector])

    by_check: dict[str, list[tuple[str, str]]] = {}
    for nodeid, outcome in collector.outcomes.items():
        name = nodeid.rsplit("::", 1)[-1]
        check, _, rest = name.partition("[")
        map_name = rest.rstrip("]") if rest else "-"
        by_check.setdefault(check, []).append((map_name, outcome))

    failed_any = False
    for check in sorted(by_check):
        results = by_check[check]
        failures = [m for m, o in results if o != "passed"]
        if failures:
            failed_any = True
        status = (
            f"FAILED: {', '.join(failures)}"
            if failures
            else ("skipped" if all(o == "skipped" for _, o in results) else "green")
        )
        print(
            f"{check:<35} {len(results) - len(failures):>2}/{len(results):<2}  {status}"
        )
    return 1 if failed_any else 0


def _write_golden(case: str) -> None:
    with _deterministic_rendering():
        text = CASES[case]()
    path = GOLDENS_ROOT / f"{case}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Default text mode, matching `generate_movement_lab_pairs.py`: the repo runs with
    # `core.autocrlf=true`, so this leaves the file untouched on a clean re-run.
    with open(path, "w", encoding="utf-8") as file:
        file.write(text)
    print(f"{case:<24} written ({path})")


def _check_goldens() -> int:
    drifted = []
    with _deterministic_rendering():
        rendered = {case: CASES[case]() for case in sorted(CASES)}
    for case, text in rendered.items():
        path = GOLDENS_ROOT / f"{case}.txt"
        existing = path.read_text(encoding="utf-8") if path.exists() else None
        status = "unchanged" if existing == text else "CHANGED"
        if existing != text:
            drifted.append(case)
        print(f"{case:<24} {status}")
    if drifted:
        print(f"\nWould rewrite: {', '.join(drifted)}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--golden", metavar="CASE", help="Regenerate one golden case under goldens/."
    )
    parser.add_argument(
        "--all-goldens", action="store_true", help="Regenerate every golden case."
    )
    parser.add_argument(
        "--check-goldens",
        action="store_true",
        help="Report which goldens would change, writing nothing.",
    )
    args = parser.parse_args(argv)

    if args.golden:
        if args.golden not in CASES:
            parser.error(
                f"Unknown case {args.golden!r}. Known: {', '.join(sorted(CASES))}"
            )
        _write_golden(args.golden)
        return 0
    if args.all_goldens:
        for case in sorted(CASES):
            _write_golden(case)
        return 0
    if args.check_goldens:
        return _check_goldens()
    return _sweep()


if __name__ == "__main__":
    raise SystemExit(main())
