"""
Regenerate the movement lab's frozen samples under
`tests/test_maple/movement_lab/pairs/`.

The samples are checked in, so regenerating is a command rather than a memory. Run it
from the repo root:

    python toolkit/generate_movement_lab_pairs.py            # every map
    python toolkit/generate_movement_lab_pairs.py GhostShip1 # one map
    python toolkit/generate_movement_lab_pairs.py --check    # write nothing, report drift

A regenerated file is identical to the checked-in one unless the map's JSON changed,
the Corpus manifest changed, or **the code that decides reachability changed**. That
last case is the point: reachability is frozen as data, so a pair that stops being
reachable fails the lab's checks instead of being silently skipped. When the change was
deliberate, rerun this and commit the diff; when it was not, it is a defect.
"""

import argparse
import sys
from pathlib import Path

# Running a script by path puts `toolkit/` on `sys.path`, not the repo root, so the
# root goes on explicitly - otherwise `python toolkit/generate_movement_lab_pairs.py`
# cannot see `tests` or `maple` at all.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_maple.movement_lab import corpus


def _write(entry: corpus.CorpusMap, text: str) -> None:
    # Default text mode, so the newlines match what git checks out on this platform
    # (the repo runs with `core.autocrlf=true`) and a rerun leaves the file untouched.
    entry.pairs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(entry.pairs_path, "w", encoding="utf-8") as file:
        file.write(text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "maps",
        nargs="*",
        help="Map names to regenerate. Defaults to every map in the Corpus.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Report which samples would change and exit non-zero, writing nothing.",
    )
    args = parser.parse_args(argv)

    wanted = set(args.maps)
    unknown = wanted - {entry.name for entry in corpus.CORPUS}
    if unknown:
        parser.error(f"Not in the Corpus: {', '.join(sorted(unknown))}")
    entries = [e for e in corpus.CORPUS if not wanted or e.name in wanted]

    drifted = []
    for entry in entries:
        pairs = corpus.freeze_sample(entry)
        text = corpus.render_sample(entry, pairs)
        reachable = sum(pair.reachable for pair in pairs)
        existing = (
            entry.pairs_path.read_text(encoding="utf-8")
            if entry.pairs_path.exists()
            else None
        )
        status = "unchanged" if existing == text else "CHANGED"
        if existing != text:
            drifted.append(entry.name)
            if not args.check:
                _write(entry, text)
                status = "written"
        print(
            f"{entry.name:<16} {len(pairs):>4} pairs  "
            f"{reachable:>4} reachable  {len(pairs) - reachable:>4} unreachable  "
            f"nodes={len(corpus.walkable_nodes(entry)):<5} {status}"
        )

    if args.check and drifted:
        print(f"\nWould rewrite: {', '.join(drifted)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
