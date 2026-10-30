"""
The catalogue's mobs, skills and character actions, built from the raw layer of
a synthetic client's extraction.

`write_game_client` writes `test_catalogue`'s client of maps, whose Henesys
places a Snail, and adds, every value invented:

- in a `.ms` pack, as Classic keeps them, three mobs: Snail (`0100100`), with
  a `stand` of two canvases and a UOL and a `hit1`; Blue Snail (`0100101`),
  which links to Snail's sprites; and Stump (`0130100`), a boss that flies.
- in another pack, the skills of jobs 200, 210 and 220: Magic Claw, with two
  levels and two actions; Energy Bolt, whose `common` holds a range and whose
  action is a single string; and two skills named MP Eater, one of which has
  only `common`, three levels of it. And `Skill/Attacktype.img`, which isn't a
  job's.
- `Character/00002000.img`, the body's actions: `swingO1` takes 800 ms,
  `alert3` borrows `alert`'s poses with negative delays, and `prone` has no
  delay. And the head, `00012000.img`, whose actions aren't read.
"""

import dataclasses
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from game_data.catalogue import (
    Catalogue,
    CatalogueError,
    MapRef,
    MobFrame,
    Ref,
    SkillLevel,
    build,
    build_catalogue,
)
from game_data.cli import main
from game_data.extraction import extract
from tests.test_game_data import wz_writer as w
from tests.test_game_data.test_catalogue import (
    HENESYS,
    canvas,
    rows,
    write_map_client,
    write_raw,
)

SNAIL = 100100
BLUE_SNAIL = 100101
STUMP = 130100
MAGIC_CLAW = 2001003
ENERGY_BOLT = 2001002


def _ints(**values: int) -> list[w.Property]:
    return [w.Int(key, value) for key, value in values.items()]


def mob_info(*extra: w.Property, level: int) -> w.Prop:
    """A mob's `info`: the stats every mob has, then `extra`."""
    return w.Prop(
        "info",
        [
            *_ints(level=level, maxHP=30 * level, maxMP=5, PADamage=8, MADamage=0),
            *_ints(PDDamage=2, MDDamage=3, acc=10, eva=1, pushed=1),
            *extra,
        ],
    )


def mobs() -> list[w.Img | w.Blob]:
    return [
        w.Img(
            "Mob/0100100.img",
            [
                mob_info(
                    w.Int("speed", -60),
                    w.Int("exp", 3),
                    w.Int("bodyAttack", 1),
                    w.String("elemAttr", "F2"),
                    level=1,
                ),
                w.Prop(
                    "stand",
                    [
                        canvas(
                            "0",
                            40,
                            w.Vector("origin", 10, 20),
                            w.Vector("lt", -5, -15),
                            w.Vector("rb", 5, 0),
                            w.Vector("head", 1, -14),
                            w.Int("delay", 180),
                        ),
                        canvas(
                            "1",
                            41,
                            w.Vector("origin", 11, 21),
                            w.String("delay", "120"),
                        ),
                        w.Uol("2", "0"),
                        w.Int("zigzag", 1),
                    ],
                ),
                w.Prop("hit1", [canvas("0", 42, w.Vector("origin", 12, 22))]),
            ],
        ),
        w.Img(
            "Mob/0100101.img",
            [mob_info(w.String("link", "0100100"), w.Int("speed", -50), level=2)],
        ),
        w.Img(
            "Mob/0130100.img",
            [
                mob_info(
                    *_ints(flySpeed=40, boss=1, undead=1, firstAttack=1), level=10
                ),
                w.Prop(
                    "fly",
                    [canvas("0", 43, w.Vector("origin", 0, 0), w.Int("delay", 100))],
                ),
            ],
        ),
    ]


def skills() -> list[w.Img | w.Blob]:
    def skill(skill_id: int, *children: w.Property) -> w.Prop:
        return w.Prop(f"{skill_id:07d}", list(children))

    def level(number: int, *fields: w.Property) -> w.Prop:
        return w.Prop(str(number), [w.String("hs", f"h{number}"), *fields])

    return [
        w.Img(
            "Skill/200.img",
            [
                w.Prop("info", [canvas("icon", 50)]),
                w.Prop(
                    "skill",
                    [
                        skill(
                            ENERGY_BOLT,
                            w.String("action", "swingO2"),
                            w.Prop(
                                "common",
                                [
                                    w.String("bulletCount", "1"),
                                    w.String("range", "350"),
                                ],
                            ),
                            w.Prop(
                                "level",
                                [
                                    level(1, *_ints(mpCon=6, mad=15)),
                                    level(2, w.String("mpCon", "7"), w.Int("mad", 18)),
                                ],
                            ),
                        ),
                        skill(
                            MAGIC_CLAW,
                            canvas("icon", 51, w.Vector("origin", 0, 32)),
                            w.Prop("info", [w.Int("type", 1)]),
                            w.Prop(
                                "action",
                                [w.String("0", "swingO1"), w.String("1", "swingO2")],
                            ),
                            w.Prop(
                                "level",
                                [
                                    level(2, *_ints(mpCon=11, mad=46, mobCount=1)),
                                    level(
                                        1,
                                        *_ints(mpCon=10, mad=45, mobCount=1),
                                        *_ints(attackCount=2, time=30, cooltime=5),
                                        w.Vector("lt", -100, -20),
                                        w.Vector("rb", 0, 10),
                                        w.Long("x", 7),
                                        w.Float("f", 0.5),
                                        w.Prop("ball", [canvas("0", 52)]),
                                    ),
                                ],
                            ),
                        ),
                    ],
                ),
            ],
        ),
        w.Img(
            "Skill/210.img",
            [
                w.Prop(
                    "skill",
                    [skill(2100000, w.Prop("level", [level(1, w.Int("x", 10))]))],
                )
            ],
        ),
        w.Img(
            "Skill/220.img",
            [
                w.Prop(
                    "skill",
                    [
                        skill(
                            2200000,
                            w.Prop(
                                "common",
                                [w.Int("maxLevel", 3), w.String("cooltime", "5")],
                            ),
                        )
                    ],
                )
            ],
        ),
        w.Img(
            "Skill/Attacktype.img",
            [w.Prop("1000", [w.String("info", "poison")])],
        ),
    ]


def body() -> list[w.Property]:
    def frame(name: str, *children: w.Property) -> w.Prop:
        return w.Prop(name, list(children))

    def borrowed(name: str, pose: int, delay: int) -> w.Prop:
        return frame(
            name,
            w.String("action", "alert"),
            w.Int("frame", pose),
            w.Int("delay", delay),
        )

    return [
        w.Prop("info", [w.String("islot", "Bd")]),
        w.Prop(
            "swingO1",
            [
                frame("0", canvas("body", 60), w.Int("delay", 300)),
                frame("1", w.Int("delay", 150)),
                frame("2", w.Int("delay", 350)),
            ],
        ),
        w.Prop(
            "swingO2",
            [frame("0", w.Int("delay", 200)), frame("1", w.String("delay", "100"))],
        ),
        w.Prop("alert", [frame("0", w.Int("delay", 500))]),
        w.Prop(
            "alert3",
            [borrowed("0", 0, -500), borrowed("1", 0, -500), borrowed("2", 0, 500)],
        ),
        w.Prop("prone", [frame("0", canvas("body", 61))]),
    ]


def write_game_client(data: Path) -> Path:
    """The client described above, in `data`."""
    write_map_client(data)
    w.write_pack(data / "Packs" / "Mob_00000.ms", mobs())
    w.write_pack(data / "Packs" / "Skill_00000.ms", skills())
    w.write_tree(
        data / "Character",
        [
            w.Img("00002000.img", body()),
            w.Img(
                "00012000.img",
                [w.Prop("swingO1", [w.Prop("0", [w.Int("delay", 999)])])],
            ),
        ],
        ini=False,
    )
    return data


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "store"


@pytest.fixture
def extracted(tmp_path: Path, root: Path) -> str:
    """The client extracted with its catalogue; the build id."""
    client = write_game_client(tmp_path / "Data")
    return extract(client, root, catalogue=build_catalogue).manifest.build


@pytest.fixture
def cat(extracted: str, root: Path) -> Iterator[Catalogue]:
    with Catalogue.open(extracted, root) as catalogue:
        yield catalogue


# --- mobs --------------------------------------------------------------------


def test_a_mob_holds_its_stats_with_what_it_lacks_as_none(cat: Catalogue) -> None:
    snail = cat.mob("Snail")
    stump = cat.mob(STUMP)

    assert (snail.id, snail.name, snail.link, snail.level) == (SNAIL, "Snail", None, 1)
    assert (snail.max_hp, snail.max_mp, snail.speed, snail.exp) == (30, 5, -60, 3)
    assert (snail.pa_damage, snail.ma_damage) == (8, 0)
    assert (snail.pd_damage, snail.md_damage) == (2, 3)
    assert (snail.acc, snail.eva, snail.pushed) == (10, 1, 1)
    assert snail.body_attack
    assert not snail.boss
    assert not snail.undead
    assert not snail.first_attack
    assert snail.elem_attr == "F2"
    assert (stump.speed, stump.fly_speed, stump.exp, stump.elem_attr) == (
        None,
        40,
        None,
        None,
    )
    assert stump.boss
    assert stump.undead
    assert stump.first_attack
    assert not stump.body_attack


def test_a_mobs_frames_follow_their_links_and_skip_what_isnt_a_frame(
    cat: Catalogue,
) -> None:
    frames = cat.mob(SNAIL).frames

    images = [frame.image for frame in frames]
    assert frames == (
        MobFrame("stand", 0, images[0], 10, 20, -5, -15, 5, 0, 1, -14, 180),
        MobFrame(
            "stand", 1, images[1], 11, 21, None, None, None, None, None, None, 120
        ),
        MobFrame("stand", 2, images[0], 10, 20, -5, -15, 5, 0, 1, -14, 180),
        MobFrame(
            "hit1", 0, images[3], 12, 22, None, None, None, None, None, None, None
        ),
    )
    assert len(set(images)) == 3
    assert None not in images


def test_a_linked_mob_records_its_link_and_has_the_linked_mobs_frames(
    cat: Catalogue, extracted: str, root: Path
) -> None:
    blue = cat.mob("blue snail")

    assert (blue.link, blue.level, blue.max_hp, blue.speed) == (SNAIL, 2, 60, -50)
    assert blue.frames == cat.mob(SNAIL).frames
    sql = "SELECT action, frame, image, delay FROM mob_frames WHERE mob = {} ORDER BY rowid"
    assert rows(root, extracted, sql.format(BLUE_SNAIL)) == rows(
        root, extracted, sql.format(SNAIL)
    )


@pytest.mark.parametrize("wanted", [SNAIL, "100100", "0100100", "Snail", " sNaIl "])
def test_a_mob_is_found_by_id_or_by_name_case_aside(
    cat: Catalogue, wanted: str | int
) -> None:
    assert cat.mob(wanted) == cat.mob(SNAIL)


def test_an_unknown_mob_lists_the_closest_names(cat: Catalogue) -> None:
    with pytest.raises(LookupError) as raised:
        cat.mob("Snial")

    assert str(raised.value.args[0]).startswith(
        "no mob is named 'Snial'; the closest are: Snail"
    )
    with pytest.raises(LookupError, match="no mob has the ID 404"):
        cat.mob(404)


def test_a_map_is_not_a_mob(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match="no mob is named 'Henesys'"):
        cat.mob("Henesys")


def test_maps_spawning_lists_the_maps_a_mob_is_placed_on(cat: Catalogue) -> None:
    assert cat.maps_spawning("Snail") == [MapRef(HENESYS, "Victoria Road: Henesys", 1)]
    assert cat.maps_spawning(STUMP) == []


# --- skills ------------------------------------------------------------------


def test_a_skill_holds_its_job_names_type_actions_and_icon(cat: Catalogue) -> None:
    claw = cat.skill("Magic Claw")

    assert (claw.id, claw.job, claw.name, claw.description) == (
        MAGIC_CLAW,
        200,
        "Magic Claw",
        "Two claws.",
    )
    assert (claw.type, claw.max_level, claw.actions) == (1, 2, ("swingO1", "swingO2"))
    assert claw.icon is not None
    assert [level.level for level in claw.levels] == [1, 2]


def test_a_level_has_the_common_columns_and_every_other_field_as_json(
    cat: Catalogue,
) -> None:
    first = cat.skill(MAGIC_CLAW).level(1)

    assert first == SkillLevel(
        skill=MAGIC_CLAW,
        level=1,
        actions=("swingO1", "swingO2"),
        mp_con=10,
        time=30,
        lt_x=-100,
        lt_y=-20,
        rb_x=0,
        rb_y=10,
        mob_count=1,
        attack_count=2,
        range=None,
        cooltime=5,
        other=first.other,
    )
    ball = first.other.pop("ball")
    assert first.other == {"hs": "h1", "mad": 45, "x": 7, "f": 0.5}
    assert isinstance(ball, dict)
    frame = ball["0"]
    assert isinstance(frame, dict)
    assert frame["$type"] == "canvas"


def test_common_fields_hold_at_every_level(cat: Catalogue) -> None:
    bolt = cat.skill("Energy Bolt")

    assert bolt.actions == ("swingO2",)
    assert [(lv.mp_con, lv.range) for lv in bolt.levels] == [(6, 350), (7, 350)]
    assert [lv.other for lv in bolt.levels] == [
        {"hs": "h1", "mad": 15, "bulletCount": 1},
        {"hs": "h2", "mad": 18, "bulletCount": 1},
    ]


def test_a_skill_of_common_fields_only_has_max_level_levels_of_them(
    cat: Catalogue,
) -> None:
    eater = cat.skill(2200000)

    assert eater.max_level == 3
    assert [(lv.level, lv.cooltime, lv.other) for lv in eater.levels] == [
        (1, 5, {}),
        (2, 5, {}),
        (3, 5, {}),
    ]
    assert (eater.actions, eater.icon, eater.type) == ((), None, None)


def test_a_missing_level_says_which_levels_there_are(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match="Magic Claw has no level 3; it has 1 to 2"):
        cat.skill(MAGIC_CLAW).level(3)


def test_an_ambiguous_skill_name_lists_every_skill_with_its_id(cat: Catalogue) -> None:
    with pytest.raises(LookupError) as raised:
        cat.skill("mp eater")

    assert str(raised.value.args[0]) == (
        "'mp eater' names 2 skills: MP Eater (2100000), MP Eater (2200000). "
        "Ask for one by ID"
    )


def test_images_that_arent_a_jobs_hold_no_skills(
    cat: Catalogue, extracted: str, root: Path
) -> None:
    assert rows(root, extracted, "SELECT id, job FROM skills ORDER BY id") == [
        (ENERGY_BOLT, 200),
        (MAGIC_CLAW, 200),
        (2100000, 210),
        (2200000, 220),
    ]


# --- actions and durations ---------------------------------------------------


def test_an_actions_duration_is_its_frames_delays_added_up(cat: Catalogue) -> None:
    assert cat.action_duration("swingO1") == 800
    assert cat.action_duration("swingO2") == 300


def test_negative_delays_count_by_their_magnitude(
    cat: Catalogue, extracted: str, root: Path
) -> None:
    assert cat.action_duration("alert3") == 1500
    assert rows(
        root, extracted, "SELECT * FROM actions WHERE action = 'alert3' ORDER BY frame"
    ) == [
        ("alert3", 0, -500, 1500),
        ("alert3", 1, -500, 1500),
        ("alert3", 2, 500, 1500),
    ]


def test_an_action_without_delays_or_unknown_has_no_duration(cat: Catalogue) -> None:
    with pytest.raises(LookupError, match="none of the action 'prone''s frames"):
        cat.action_duration("prone")
    with pytest.raises(LookupError, match="no action 'swingO9'; the closest are"):
        cat.action_duration("swingO9")


def test_a_skills_duration_is_its_first_actions(cat: Catalogue) -> None:
    assert cat.skill_duration("Magic Claw") == 800
    assert cat.skill_duration(ENERGY_BOLT) == 300
    with pytest.raises(LookupError, match="plays no action"):
        cat.skill_duration(2200000)


# --- search and frozen results -----------------------------------------------


def test_search_covers_maps_mobs_and_skills(cat: Catalogue) -> None:
    assert cat.search("snail") == [
        Ref("mob", SNAIL, "Snail"),
        Ref("mob", BLUE_SNAIL, "Blue Snail"),
    ]
    assert cat.search("claw") == [Ref("skill", MAGIC_CLAW, "Magic Claw")]
    assert cat.search("e", kind="skill") == [
        Ref("skill", ENERGY_BOLT, "Energy Bolt"),
        Ref("skill", 2100000, "MP Eater"),
        Ref("skill", 2200000, "MP Eater"),
    ]
    assert cat.search(str(STUMP)) == [Ref("mob", STUMP, "Stump")]


def test_mob_and_skill_lookups_return_frozen_dataclasses(cat: Catalogue) -> None:
    mob = cat.mob(SNAIL)
    skill = cat.skill(MAGIC_CLAW)
    found = cat.maps_spawning(SNAIL)[0]

    for value in (mob, mob.frames[0], skill, skill.levels[0], found):
        assert dataclasses.is_dataclass(value)
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(value, dataclasses.fields(value)[0].name, 0)
    assert hash(skill.levels[0]) == hash(cat.skill(MAGIC_CLAW).levels[0])


# --- the command line --------------------------------------------------------


def test_show_mob_prints_a_mob_found_by_name_as_json(
    extracted: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del extracted
    code = main(["show", "mob", "Blue Snail", "--root", str(root)])

    shown = json.loads(capsys.readouterr().out)
    assert code == 0
    assert (shown["id"], shown["name"], shown["link"]) == (
        BLUE_SNAIL,
        "Blue Snail",
        SNAIL,
    )
    assert [f["action"] for f in shown["frames"]] == ["stand", "stand", "stand", "hit1"]


def test_show_skill_prints_every_level_or_the_one_asked_for(
    extracted: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del extracted
    assert main(["show", "skill", "magic claw", "--root", str(root)]) == 0
    whole = json.loads(capsys.readouterr().out)

    assert (
        main(["show", "skill", "Magic Claw", "--level", "2", "--root", str(root)]) == 0
    )
    level = json.loads(capsys.readouterr().out)

    assert (whole["id"], whole["max_level"], len(whole["levels"])) == (MAGIC_CLAW, 2, 2)
    assert (level["level"], level["mp_con"], level["actions"]) == (
        2,
        11,
        ["swingO1", "swingO2"],
    )
    assert level["other"] == {"hs": "h2", "mad": 46}


def test_show_skill_with_a_missing_level_is_an_error(
    extracted: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del extracted
    code = main(["show", "skill", "Magic Claw", "--level", "9", "--root", str(root)])

    assert code == 1
    assert "has no level 9" in capsys.readouterr().err


def test_a_level_for_anything_but_a_skill_is_a_usage_error(
    extracted: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del extracted
    with pytest.raises(SystemExit) as raised:
        main(["show", "mob", "Snail", "--level", "2", "--root", str(root)])

    assert raised.value.code == 2
    assert "use it with `show skill`" in capsys.readouterr().err


def test_search_by_kind_prints_mobs_and_skills_as_json(
    extracted: str, root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    del extracted
    assert main(["search", "snail", "--kind", "mob", "--root", str(root)]) == 0
    mobs_found = json.loads(capsys.readouterr().out)
    assert main(["search", "Claw", "--root", str(root)]) == 0
    everything = json.loads(capsys.readouterr().out)

    assert [m["id"] for m in mobs_found] == [SNAIL, BLUE_SNAIL]
    assert everything == [{"kind": "skill", "id": MAGIC_CLAW, "name": "Magic Claw"}]


# --- a raw layer the catalogue doesn't understand -----------------------------

CANVAS = {"$type": "canvas", "image": "a", "w": 1, "h": 1}
STATS = dict.fromkeys(
    ("level", "maxHP", "maxMP", "PADamage", "MADamage", "PDDamage", "MDDamage"), 1
) | dict.fromkeys(("acc", "eva", "pushed"), 1)


@pytest.mark.parametrize(
    ("trees", "message"),
    [
        (
            {"Mob/0000001.img": {"info": {"level": 1}}},
            "image Mob/0000001.img, node info: it has no child 'maxHP'",
        ),
        (
            {
                "Mob/0000001.img": {
                    "info": STATS | {"link": "0000002"},
                    "stand": {"0": CANVAS},
                },
                "Mob/0000002.img": {"info": STATS, "stand": {"0": CANVAS}},
            },
            "Mob/0000001.img: it links to another mob's sprites, and has its own",
        ),
        (
            {"Mob/0000001.img": {"info": STATS | {"link": "0000009"}}},
            (
                "image Mob/0000001.img, node info/link: it links to mob 9, which the raw "
                "layer doesn't have"
            ),
        ),
        (
            {"Mob/0000001.img": {"info": STATS, "stand": {"0": 5}}},
            "image Mob/0000001.img, node stand/0: it is a int, not a canvas",
        ),
        (
            {
                "Skill/200.img": {
                    "skill": {
                        "2000000": {
                            "common": {"mpCon": "5"},
                            "level": {"1": {"mpCon": 5}},
                        }
                    }
                }
            },
            (
                "image Skill/200.img, node skill/2000000/level/1/mpCon: common/mpCon sets "
                "it too"
            ),
        ),
        (
            {
                "Skill/200.img": {
                    "skill": {
                        "2000000": {
                            "common": {"maxLevel": 2},
                            "level": {"1": {"mpCon": 5}},
                        }
                    }
                }
            },
            (
                "image Skill/200.img, node skill/2000000/common/maxLevel: it says 2 "
                "levels, and there are 1"
            ),
        ),
        (
            {"Skill/200.img": {"skill": {"2000000": {"level": {"1": {"mpCon": "x"}}}}}},
            (
                "image Skill/200.img, node skill/2000000/level/1/mpCon: it is a string, "
                "not an integer"
            ),
        ),
        (
            {"Character/00002000.img": {"walk1": {"info": {}}}},
            (
                "image Character/00002000.img, node walk1/info: a frame that isn't "
                "numbered"
            ),
        ),
    ],
)
def test_a_mob_skill_or_action_out_of_shape_names_its_node(
    tmp_path: Path, trees: dict[str, Any], message: str
) -> None:
    folder = write_raw(tmp_path / "x", trees)

    with pytest.raises(CatalogueError) as raised:
        build(folder)

    assert str(raised.value) == message
