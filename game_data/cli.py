"""
`python -m game_data <command>`: the command line, and the only module in
`game_data` that prints.

- `extract [--client PATH] [--root PATH]`: extract the installed client into
  the store, and say what was done.
- `status [--client PATH] [--root PATH]`: `missing`, `fresh` or `stale`.

`--client` overrides `configs/game_data.ini` (`config`). `--root` is the
store, `data/game_data` by default.

It sits beside the layers, not in one, and wires them together: the catalogue
and report hooks `extract` calls are chosen here.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .archive import ArchiveError
from .config import STORE, ClientPathNotSet, client_data_path
from .extraction import (
    CatalogueHook,
    Extracted,
    ExtractionError,
    Freshness,
    ReportHook,
    extract,
    no_catalogue,
    no_report,
    status,
)

# The catalogue (#264) and the patch report (#266) are built through these.
CATALOGUE: CatalogueHook = no_catalogue
REPORT: ReportHook = no_report

# How many failures `extract` lists before it only counts them.
SHOWN_FAILURES = 20


def main(argv: Sequence[str] | None = None) -> int:
    """Runs one command. Returns the exit code: 0, or 1 on an error."""
    arguments = _parser().parse_args(argv)
    try:
        client = client_data_path(arguments.client)
        if arguments.command == "extract":
            return _extract(client, arguments.root)
        return _status(client, arguments.root)
    except (ClientPathNotSet, NotADirectoryError, ArchiveError, ExtractionError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m game_data",
        description="Extract and query MapleStory Classic's client data.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("extract", "extract the installed client into the store"),
        ("status", "does the installed client match the latest extraction?"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument(
            "--client",
            type=Path,
            help="the client's MSCW\\Data folder, instead of configs/game_data.ini",
        )
        command.add_argument(
            "--root", type=Path, default=STORE, help=f"the store (default {STORE})"
        )
    return parser


def _extract(client: Path, root: Path) -> int:
    print(f"extracting {client} into {root}")
    done = extract(client, root, catalogue=CATALOGUE, report=REPORT, progress=_progress)
    print(_summary(done))
    return 0


def _progress(done: int, total: int) -> None:
    if done == total or done % 100 == 0:
        end = "\n" if done == total else ""
        print(f"\r{done}/{total} images", end=end, file=sys.stderr, flush=True)


def _summary(done: Extracted) -> str:
    manifest = done.manifest
    lines: list[str] = []
    if not done.created:
        lines.append(
            f"build {manifest.build} was already extracted: it is the latest again"
        )
    else:
        lines.append(
            f"extracted build {manifest.build} in {done.seconds:.0f} s: "
            f"{manifest.images} images, {manifest.canvases} canvases, "
            f"{done.written} new images in the image store"
        )
        for failure in manifest.failures[:SHOWN_FAILURES]:
            lines.append(f"  failed: {failure.image} {failure.node}: {failure.reason}")
        if len(manifest.failures) > SHOWN_FAILURES:
            lines.append(
                f"  ... and {len(manifest.failures) - SHOWN_FAILURES} more, "
                "listed in the manifest"
            )
        if done.report is not None:
            lines.append(f"report: {done.report}")
    count = len(manifest.failures)
    lines.append(
        f"{count} canvas{'es' if count != 1 else ''} failed "
        "(a link naming nothing), recorded in the manifest"
        if count
        else "0 failures"
    )
    return "\n".join(lines)


def _status(client: Path, root: Path) -> int:
    found = status(client, root)
    match found.freshness:
        case Freshness.MISSING:
            print(
                f"missing: {root} has no extraction; run `python -m game_data extract`"
            )
        case Freshness.FRESH:
            print(f"fresh: the installed client is build {found.latest}, the latest")
        case Freshness.STALE:
            print(
                f"stale: the installed client isn't build {found.latest}, the latest; "
                f"{len(found.changed)} archives differ. "
                "Run `python -m game_data extract`"
            )
    return 0
