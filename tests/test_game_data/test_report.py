"""
The patch report, built from two extractions of a synthetic client.

Build A is `test_catalogue_mobs_skills`' client. Build B is A changed in four
ways, and only four:

- a foothold of Henesys: its second segment ends 2 pixels lower;
- a mob stat: Snail's `acc` is 11, not 10;
- an added skill: Teleport (`2300000`), named in `String/Skill.img`;
- a canvas's pixels (and so its image name): the body's `prone` canvas, in
  `Character/00002000.img`, which is otherwise unchanged.
"""

import dataclasses
import re
from pathlib import Path

import pytest

from game_data.catalogue import Catalogue, build_catalogue
from game_data.cli import main
from game_data.extraction import RAW, ExtractionError, Store, extract
from game_data.report import (
    diff_raw,
    diff_trees,
    render,
    summarize,
    write_report,
)
from game_data.report.summary import _map_change, _skill_change, anonymous
from tests.test_game_data import test_catalogue as tc
from tests.test_game_data import test_catalogue_mobs_skills as tm
from tests.test_game_data import wz_writer as w

TELEPORT = 2300000
PRONE_RED = 61


def _write_b(monkeypatch: pytest.MonkeyPatch, data: Path) -> Path:
    """Build B of the client, in `data`."""
    original_footholds = tc.foothold_tree
    original_info = tm.mob_info
    original_skills = tm.skills
    original_strings = tc.strings
    original_canvas = tm.canvas

    def footholds(*found: tuple[int, int, int, int, int, int, int]) -> w.Prop:
        return original_footholds(
            *(
                (i, a, b, c, 12 if (i, d) == (2, 10) else d, e, f)
                for i, a, b, c, d, e, f in found
            )
        )

    def info(*extra: w.Property, level: int) -> w.Prop:
        found = original_info(*extra, level=level)
        children = [
            w.Int("acc", 11)
            if isinstance(c, w.Int) and c.name == "acc" and level == 1
            else c
            for c in found.children
        ]
        return dataclasses.replace(found, children=children)

    def skills() -> list[w.Img | w.Blob]:
        teleport = w.Prop(
            f"{TELEPORT:07d}",
            [w.Prop("level", [w.Prop("1", [w.Int("mpCon", 9)])])],
        )
        return [
            *original_skills(),
            w.Img("Skill/230.img", [w.Prop("skill", [teleport])]),
        ]

    def strings() -> list[w.Img]:
        return [
            dataclasses.replace(
                img,
                children=[
                    *img.children,
                    w.Prop(str(TELEPORT), [w.String("name", "Teleport")]),
                ],
            )
            if img.name == "Skill.img"
            else img
            for img in original_strings()
        ]

    def canvas(name: str, red: int, *children: w.Property) -> w.Canvas:
        return original_canvas(name, 161 if red == PRONE_RED else red, *children)

    monkeypatch.setattr(tc, "foothold_tree", footholds)
    monkeypatch.setattr(tm, "mob_info", info)
    monkeypatch.setattr(tm, "skills", skills)
    monkeypatch.setattr(tc, "strings", strings)
    monkeypatch.setattr(tm, "canvas", canvas)
    return tm.write_game_client(data)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "store"


@pytest.fixture
def builds(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str]:
    """Extracts A, then B, into the store: their build ids."""
    first = extract(
        tm.write_game_client(tmp_path / "A"), root, catalogue=build_catalogue
    )
    with monkeypatch.context() as patch:
        client_b = _write_b(patch, tmp_path / "B")
    second = extract(client_b, root, catalogue=build_catalogue)
    assert first.manifest.build != second.manifest.build
    return first.manifest.build, second.manifest.build


def _raw(root: Path, build: str) -> Path:
    return root / "extractions" / build / RAW


# --- the raw diff ------------------------------------------------------------


def test_the_raw_diff_lists_added_and_changed_images_and_skips_unchanged_ones(
    root: Path, builds: tuple[str, str]
) -> None:
    old, new = builds

    raw = diff_raw(_raw(root, old), _raw(root, new))

    assert raw.removed == ()
    assert len(raw.added) == 1
    assert raw.added[0].endswith("230.img")
    changed = {image.path for image in raw.changed}
    assert len(changed) == len(raw.changed) == 4
    assert any(path.endswith("000000100.img") for path in changed)  # the foothold
    assert any(path.endswith("0100100.img") for path in changed)  # the mob stat
    assert any(path.endswith("00002000.img") for path in changed)  # the canvas
    assert any(path.endswith("Skill.img") for path in changed)  # Teleport's name


def test_a_changed_canvas_is_one_changed_image_name_inside_an_otherwise_same_image(
    root: Path, builds: tuple[str, str]
) -> None:
    old, new = builds

    raw = diff_raw(_raw(root, old), _raw(root, new))

    body = next(i for i in raw.changed if i.path.endswith("00002000.img"))
    assert [(n.path, n.kind) for n in body.nodes] == [("prone/0/body/image", "changed")]
    (node,) = body.nodes
    assert isinstance(node.old, str)
    assert isinstance(node.new, str)
    assert node.old != node.new


def test_the_raw_diff_gives_a_changed_mob_stat_as_path_old_and_new_value(
    root: Path, builds: tuple[str, str]
) -> None:
    old, new = builds

    raw = diff_raw(_raw(root, old), _raw(root, new))

    mob = next(i for i in raw.changed if i.path.endswith("0100100.img"))
    assert [(n.path, n.old, n.new) for n in mob.nodes] == [("info/acc", 10, 11)]


def test_diffing_a_store_with_itself_finds_nothing(
    root: Path, builds: tuple[str, str]
) -> None:
    raw = diff_raw(_raw(root, builds[0]), _raw(root, builds[0]))

    assert (raw.added, raw.removed, raw.changed) == ((), (), ())


def test_nodes_are_compared_by_kind_and_by_position_in_the_tree() -> None:
    old = {"a": {"b": 1, "c": 2.0, "d": {"$type": "short", "value": 1}}, "gone": 1}
    new = {"a": {"b": 1, "c": 2, "d": {"$type": "long", "value": 1}, "e": "x"}, "n": 0}

    found = [(n.path, n.kind) for n in diff_trees(old, new)]

    assert found == [
        ("a/c", "changed"),  # 2.0 is a double, 2 an int
        ("a/d", "changed"),  # another type is a replaced node, not child changes
        ("a/e", "added"),
        ("gone", "removed"),
        ("n", "added"),
    ]


# --- the typed summary -------------------------------------------------------


def _summary(root: Path, builds: tuple[str, str]):  # noqa: ANN202
    with (
        Catalogue.open(builds[0], root) as old,
        Catalogue.open(builds[1], root) as new,
    ):
        return summarize(old, new)


def test_the_summary_lists_exactly_the_four_differences_by_name(
    root: Path, builds: tuple[str, str]
) -> None:
    summary = _summary(root, builds)

    assert [(r.id, r.name) for r in summary.skills_added] == [(TELEPORT, "Teleport")]
    (mob,) = summary.mobs_changed
    assert (mob.id, mob.name) == (tm.SNAIL, "Snail")
    assert [(s.field, s.old, s.new) for s in mob.stats] == [("acc", 10, 11)]
    (changed_map,) = summary.maps_changed
    assert (changed_map.id, changed_map.name) == (tc.HENESYS, "Victoria Road: Henesys")
    (geometry,) = changed_map.changes
    assert (geometry.part, geometry.kind, geometry.subject) == (
        "foothold",
        "changed",
        "map foothold 2",
    )
    assert geometry.old != geometry.new
    assert summary.maps_added == summary.maps_removed == ()
    assert summary.mobs_added == summary.mobs_removed == ()
    assert summary.skills_removed == ()
    assert summary.skills_changed == ()


def test_a_summary_of_an_extraction_against_itself_is_empty(
    root: Path, builds: tuple[str, str]
) -> None:
    summary = _summary(root, (builds[0], builds[0]))

    assert not any(dataclasses.astuple(summary))


def test_the_summary_sees_levels_and_other_fields_of_a_skill(
    root: Path, builds: tuple[str, str]
) -> None:
    """Magic Claw is the same in both builds, so edit one copy of it."""
    with Catalogue.open(builds[0], root) as old:
        claw = old.skill(tm.MAGIC_CLAW)
        edited = dataclasses.replace(
            claw,
            levels=(
                dataclasses.replace(
                    claw.levels[0],
                    mp_con=99,
                    other={**claw.levels[0].other, "mad": 1, "fresh": 2},
                ),
                *claw.levels[2:],
            ),
        )
    change = _skill_change(claw, edited)

    assert change is not None
    assert change.levels_removed == (2,)
    (level,) = change.levels
    assert level.level == 1
    fields = {v.field: (v.old, v.new) for v in level.values}
    assert fields["mp_con"] == (10, 99)
    assert fields["other.mad"] == (45, 1)
    assert fields["other.fresh"] == (None, 2)


def test_inserting_an_object_or_tile_ahead_of_others_reports_only_the_new_segments(
    root: Path, builds: tuple[str, str]
) -> None:
    """Their IDs are running numbers, so inserting one renumbers every later."""
    with Catalogue.open(builds[0], root) as cat:
        before = cat.map(tc.HENESYS)
    others = [f for f in before.footholds if f.source != "map"]
    assert others, "the fixture's Henesys has object and tile footholds"
    inserted = dataclasses.replace(others[0], id=0, x1=7000, x2=7050)
    shifted = [
        dataclasses.replace(f, id=f.id + 1) if f.source != "map" else f
        for f in before.footholds
    ]
    after = dataclasses.replace(before, footholds=(*shifted, inserted))
    # The inserted one comes first among its source, as a layer read earlier would.
    first = next(
        i for i, f in enumerate(after.footholds) if f.source == inserted.source
    )
    ordered = list(after.footholds)
    ordered.insert(first, ordered.pop())
    after = dataclasses.replace(after, footholds=tuple(ordered))

    change = _map_change(before, after)

    assert change is not None
    assert [(c.part, c.kind) for c in change.changes] == [("foothold", "added")]
    assert "7000" in (change.changes[0].new or "")
    # and the drawing marks nothing else
    assert {anonymous(f) for f in before.footholds} <= {
        anonymous(f) for f in after.footholds
    }


# --- the page ----------------------------------------------------------------


def _page(root: Path, builds: tuple[str, str]) -> str:
    return write_report(Store(root), *builds).read_text(encoding="utf-8")


def test_the_page_is_written_to_reports_named_by_both_builds(
    root: Path, builds: tuple[str, str]
) -> None:
    path = write_report(Store(root), *builds)

    assert path == (root / "reports" / f"{builds[0]}__{builds[1]}.html").resolve()
    assert path.is_file()


def test_the_page_names_what_changed(root: Path, builds: tuple[str, str]) -> None:
    page = _page(root, builds)

    for text in [
        "Teleport (2300000)",
        "Snail (100100)",
        "Victoria Road: Henesys (100)",
    ]:
        assert text in page
    assert "map foothold 2" in page
    assert "<svg" in page


def test_the_page_is_self_contained(root: Path, builds: tuple[str, str]) -> None:
    page = _page(root, builds)

    assert "<style>" in page
    assert "data:image/png;base64," in page  # the Snail's sprite, before and after
    assert page.count('class="sprite"') == 2
    assert not re.search(r"""(?:src|href)\s*=\s*["'](?!data:|#)""", page)
    assert not re.search(r"https?://", page)
    assert "@import" not in page
    assert "url(" not in page


def test_a_sprite_the_store_lost_is_said_so_rather_than_dropped(
    root: Path, builds: tuple[str, str]
) -> None:
    store = Store(root)
    for _, file in list(store.images.files()):
        file.unlink()

    page = write_report(store, *builds).read_text(encoding="utf-8")

    assert "no longer in the image store" in page


def test_the_page_escapes_what_it_prints() -> None:
    from game_data.report.page import _value

    assert "<script>" not in _value("<script>alert(1)</script>")


def test_a_report_for_a_build_the_store_lacks_says_which_it_has(
    root: Path, builds: tuple[str, str]
) -> None:
    with pytest.raises(ExtractionError, match=builds[1]):
        write_report(Store(root), builds[0], "0123456789abcdef")


def test_rendering_a_page_with_nothing_to_report_says_so(
    root: Path, builds: tuple[str, str]
) -> None:
    store = Store(root)
    manifest = store.manifests()[0]
    raw = diff_raw(_raw(root, builds[0]), _raw(root, builds[0]))

    page = render(
        manifest, manifest, raw, _summary(root, (builds[0], builds[0])), store.images
    )

    assert "No map changed." in page
    assert "No image changed." in page


# --- extract and the command -------------------------------------------------


def test_extract_writes_the_report_when_a_new_build_lands_after_another(
    tmp_path: Path, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from game_data.cli import REPORT

    first = extract(
        tm.write_game_client(tmp_path / "A"),
        root,
        catalogue=build_catalogue,
        report=REPORT,
    )
    second = extract(
        _write_b(monkeypatch, tmp_path / "B"),
        root,
        catalogue=build_catalogue,
        report=REPORT,
    )

    assert first.report is None
    assert second.report is not None
    assert second.report.name == f"{first.manifest.build}__{second.manifest.build}.html"
    assert second.report.is_file()


def test_the_extract_command_prints_the_reports_path(
    tmp_path: Path,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = tm.write_game_client(tmp_path / "Data")
    assert main(["extract", "--client", str(client), "--root", str(root)]) == 0
    with monkeypatch.context() as patch:
        _write_b(patch, client)
    capsys.readouterr()

    assert main(["extract", "--client", str(client), "--root", str(root)]) == 0

    printed = capsys.readouterr().out
    (line,) = [x for x in printed.splitlines() if x.startswith("report: ")]
    assert Path(line.removeprefix("report: ")).is_file()


def test_the_report_command_rebuilds_it_on_demand(
    root: Path, builds: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    path = root / "reports" / f"{builds[0]}__{builds[1]}.html"
    assert not path.exists()

    assert main(["report", "--root", str(root)]) == 0

    assert capsys.readouterr().out.strip() == f"report: {path.resolve()}"
    first = path.read_text(encoding="utf-8")
    path.unlink()
    assert main(["report", builds[0], builds[1], "--root", str(root)]) == 0
    assert path.read_text(encoding="utf-8") == first


@pytest.mark.parametrize("arguments", [["only-one"], ["a", "b", "c"]])
def test_the_report_command_takes_both_builds_or_neither(
    root: Path, arguments: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit):
        main(["report", *arguments, "--root", str(root)])

    assert "OLD and NEW" in capsys.readouterr().err


def test_the_report_command_needs_two_extractions(
    tmp_path: Path, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extract(tm.write_game_client(tmp_path / "A"), root, catalogue=build_catalogue)

    assert main(["report", "--root", str(root)]) == 1

    assert "needs two" in capsys.readouterr().err


def test_the_report_command_names_a_build_the_store_lacks(
    root: Path, builds: tuple[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["report", builds[0], "feedfacefeedface", "--root", str(root)]) == 1

    assert "feedfacefeedface" in capsys.readouterr().err


def test_the_catalogue_lists_its_ids_by_kind(
    root: Path, builds: tuple[str, str]
) -> None:
    with Catalogue.open(builds[1], root) as cat:
        assert cat.ids("skill")[-1] == TELEPORT
        assert tm.SNAIL in cat.ids("mob")
        assert tc.HENESYS in cat.ids("map")
        with pytest.raises(LookupError, match="no kind"):
            cat.ids("npc")
