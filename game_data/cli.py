"""
`python -m game_data <command>`: the command line, and the only module in
`game_data` that prints.

- `extract [--client PATH] [--root PATH]`: extract the installed client into
  the store, build its catalogue, and say what was done.
- `status [--client PATH] [--root PATH]`: `missing`, `fresh` or `stale`.
- `report [OLD NEW] [--root PATH]`: rebuild the patch report from build OLD to
  build NEW, by default from the older kept extraction to the latest, and say
  where it is. `extract` writes it by itself when a new Build lands.
- `show map|mob|skill NAME [--level N] [--root PATH]`: one map, mob or
  skill, by name or ID, as JSON; with `--level`, one level of a skill.
- `search TEXT [--kind map|mob|skill] [--root PATH]`: what matches, with IDs,
  as JSON.
- `render MAP [--overlays] [--hitboxes] [--scale S] [--out PATH] [--root PATH]`:
  a map's full screen as a PNG, by default `<root>/renders/<map id>.png`.

`--client` overrides `configs/game_data.ini` (`config`). `show`, `search` and
`render` read the latest extraction's catalogue and need no client. `render`
is imported only when it runs, because it alone loads `cv2`. `--root` is the
store, `data/game_data` by default.

It sits beside the layers, not in one, and wires them together: the catalogue
and report hooks `extract` calls are chosen here.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from .archive import ArchiveError
from .catalogue import Catalogue, CatalogueError, build_catalogue
from .config import STORE, ClientPathNotSet, client_data_path
from .extraction import (
    CatalogueHook,
    Extracted,
    ExtractionError,
    Freshness,
    ReportHook,
    Store,
    extract,
    status,
)
from .report import report_path, write_report

# The catalogue and the patch report are built through these.
CATALOGUE: CatalogueHook = build_catalogue
REPORT: ReportHook = write_report

# What `show` and `search` look up.
KINDS = ("map", "mob", "skill")

# How many failures `extract` lists before it only counts them.
SHOWN_FAILURES = 20


def main(argv: Sequence[str] | None = None) -> int:
    """Runs one command. Returns the exit code: 0, or 1 on an error."""
    parser = _parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "report" and len(arguments.builds) not in (0, 2):
        parser.error("give both OLD and NEW, or neither")
    if (
        arguments.command == "show"
        and arguments.level is not None
        and (arguments.kind != "skill")
    ):
        parser.error("--level is a skill's level: use it with `show skill`")
    try:
        match arguments.command:
            case "show":
                return _show(
                    arguments.kind, arguments.name, arguments.level, arguments.root
                )
            case "search":
                return _search(arguments.text, arguments.kind, arguments.root)
            case "report":
                return _report(arguments.builds, arguments.root)
            case "render":
                return _render(
                    arguments.map,
                    arguments.root,
                    out=arguments.out,
                    scale=arguments.scale,
                    overlays=arguments.overlays,
                    hitboxes=arguments.hitboxes,
                )
            case "extract":
                return _extract(client_data_path(arguments.client), arguments.root)
            case _:
                return _status(client_data_path(arguments.client), arguments.root)
    except (
        ClientPathNotSet,
        NotADirectoryError,
        ArchiveError,
        ExtractionError,
        CatalogueError,
    ) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except LookupError as e:
        print(f"error: {e.args[0] if e.args else e}", file=sys.stderr)
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
        _root_argument(command)
    report = commands.add_parser("report", help="rebuild the patch report")
    report.add_argument(
        "builds",
        nargs="*",
        metavar="OLD NEW",
        help="the build ids to compare (default: the older kept, to the latest)",
    )
    _root_argument(report)
    show = commands.add_parser("show", help="print one map, mob or skill as JSON")
    show.add_argument("kind", choices=KINDS, help="what to show")
    show.add_argument("name", help="its name, or its ID")
    show.add_argument("--level", type=int, help="only this level of the skill")
    _root_argument(show)
    search = commands.add_parser("search", help="list what matches, as JSON")
    search.add_argument("text", help="part of a name, or an ID")
    search.add_argument("--kind", choices=KINDS, help="only this kind")
    _root_argument(search)
    render = commands.add_parser("render", help="draw a map's full screen as a PNG")
    render.add_argument("map", help="its name, or its ID")
    render.add_argument(
        "--overlays", action="store_true", help="draw footholds, ropes, portals, spawns"
    )
    render.add_argument(
        "--hitboxes", action="store_true", help="draw spawns with their hitboxes"
    )
    render.add_argument(
        "--scale", type=_scale, default=1.0, help="multiply both sides by S"
    )
    render.add_argument(
        "--out", type=Path, help="the PNG to write (default <root>/renders/<id>.png)"
    )
    _root_argument(render)
    return parser


def _scale(text: str) -> float:
    value = float(text)
    if not value > 0:
        raise argparse.ArgumentTypeError(f"a scale must be positive, not {text}")
    return value


def _root_argument(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--root", type=Path, default=STORE, help=f"the store (default {STORE})"
    )


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
        if manifest.catalogue_schema_version is not None:
            lines.append(
                f"catalogue built, schema version {manifest.catalogue_schema_version}"
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


def _report(builds: Sequence[str], root: Path) -> int:
    store = Store(root)
    if builds:
        old, new = builds
    else:
        manifests = store.manifests()
        if len(manifests) < 2:
            raise ExtractionError(
                f"{root} has {len(manifests)} extraction{'s' if len(manifests) != 1 else ''}"
                ": a report needs two; extract a new Build first"
            )
        new, old = manifests[0].build, manifests[1].build
    write_report(store, old, new)
    print(f"report: {report_path(store, old, new)}")
    return 0


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


def _show(kind: str, name: str, level: int | None, root: Path) -> int:
    with Catalogue.latest(root) as catalogue:
        match kind:
            case "map":
                found = asdict(catalogue.map(name))
            case "mob":
                found = asdict(catalogue.mob(name))
            case _:
                skill = catalogue.skill(name)
                found = asdict(skill if level is None else skill.level(level))
    print(json.dumps(found, indent=2, ensure_ascii=False))
    return 0


def _render(
    name: str,
    root: Path,
    *,
    out: Path | None,
    scale: float,
    overlays: bool,
    hitboxes: bool,
) -> int:
    # Here, not at the top: `render` loads `cv2`, which `status` must not.
    from .render import RenderError, render_map, render_path, write_png

    with Catalogue.latest(root) as catalogue:
        found = catalogue.map(name)
        try:
            pixels = render_map(
                catalogue, found.id, scale=scale, overlays=overlays, hitboxes=hitboxes
            )
        except RenderError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        path = render_path(catalogue, found.id) if out is None else out
    write_png(pixels, path)
    height, width = pixels.shape[:2]
    print(f"rendered {found.name or found.id} ({found.id}), {width}x{height}: {path}")
    return 0


def _search(text: str, kind: str | None, root: Path) -> int:
    with Catalogue.latest(root) as catalogue:
        found = catalogue.search(text, kind)
    print(json.dumps([asdict(ref) for ref in found], indent=2, ensure_ascii=False))
    return 0
