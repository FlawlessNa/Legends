"""
`ClientData` over a synthetic `Data` folder laid out as Classic's is.

The fixture client:

    Data/
      Map/            Map.wz (stub: Map, Inner), Map.ini (2 parts),
                      Map_000.wz, Map_001.wz
        Map/          Map.wz (stub: Map0), no .ini
          Map0/       Map0.wz (empty stub), Map0.ini (1 part), Map0_000.wz
      Mob/            Mob.wz, Mob.ini (LastWzIndex|-1: no parts)
      Packs/          an empty pack, and no stub, so not a tree

The packs section has its own client, `classic`, whose images are in packs.
"""

from pathlib import Path

import pytest

from game_data.archive import (
    ClientData,
    CorruptArchive,
    IntNode,
    NodeNotFound,
    PackEntry,
    PropertyNode,
    StringNode,
    UnsupportedFormat,
    UolNode,
)
from tests.test_game_data import wz_writer as w

MAP_IMAGE: list[w.Property] = [
    w.Prop("info", [w.String("bgm", "Bgm00/GoPicnic"), w.Int("town", 1)]),
    w.Prop(
        "stand",
        [
            w.Prop("0", [w.Int("delay", 100)]),
            w.Uol("1", "0"),
            w.Prop("move", [w.Uol("again", "../0")]),
        ],
    ),
    w.Prop(
        "walk",
        [
            w.Prop("move", [w.Prop("0", [w.Int("delay", 180)])]),
            w.Prop("frames", [w.Uol("first", "../move/0")]),
            w.Uol("alias", "move"),
            w.Uol("chain", "frames/first"),
            w.Uol("elsewhere", "../../000002000.img/info/bgm"),
            w.Uol("up", "../../../../Physics.img/walkForce"),
            w.Uol("nowhere", "../move/9"),
            w.Uol("too far", "../../../../../../up"),
            w.Uol("loop a", "loop b"),
            w.Uol("loop b", "loop a"),
        ],
    ),
]


@pytest.fixture
def data(tmp_path: Path) -> Path:
    root = tmp_path / "Data"
    w.write_tree(
        root / "Map",
        stub=[w.Dir("Map"), w.Dir("Inner")],
        parts=[
            [
                w.Img("Physics.img", [w.Double("walkForce", 140000.0)]),
                w.Dir("Inner", [w.Img("first.img", [w.Int("part", 0)])]),
            ],
            [
                w.Img("Effect.img", [w.Int("part", 1)]),
                w.Dir("Inner", [w.Img("second.img", [w.Int("part", 1)])]),
            ],
        ],
    )
    w.write_tree(root / "Map" / "Map", stub=[w.Dir("Map0")], ini=False)
    w.write_tree(
        root / "Map" / "Map" / "Map0",
        stub=[],
        parts=[
            [
                w.Img("000001000.img", MAP_IMAGE),
                w.Img("000002000.img", [w.Prop("info", [w.String("bgm", "Other")])]),
            ]
        ],
    )
    w.write_tree(root / "Mob", stub=[w.Dir("_Canvas")])
    w.write_pack(root / "Packs" / "Mob_00000.ms", [])
    return root


@pytest.fixture
def client(data: Path) -> ClientData:
    return ClientData(data)


# --- the namespace ---------------------------------------------------------


def test_the_top_lists_every_tree_with_a_stub(client: ClientData) -> None:
    assert list(client.root.directories) == ["Map", "Mob"]
    assert not client.root.images


def test_a_path_resolves_to_the_archive_holding_the_image(
    client: ClientData, data: Path
) -> None:
    image = client.image("Map/Map/Map0/000001000.img")

    assert image.archive == data / "Map" / "Map" / "Map0" / "Map0_000.wz"
    assert image.path == "Map/Map/Map0/000001000.img"
    assert image.parse()["info/town"] == IntNode(name="town", value=1)


def test_a_split_tree_reads_as_one_directory(client: ClientData, data: Path) -> None:
    tree = client.directory("Map")

    assert sorted(tree.images) == ["Effect.img", "Physics.img"]
    assert sorted(tree.directories) == ["Inner", "Map"]
    assert tree.images["Physics.img"].archive == data / "Map" / "Map_000.wz"
    assert tree.images["Effect.img"].archive == data / "Map" / "Map_001.wz"


def test_a_directory_split_across_parts_merges(client: ClientData, data: Path) -> None:
    inner = client.directory("Map/Inner")

    assert list(inner.images) == ["first.img", "second.img"]
    assert inner.images["second.img"].archive == data / "Map" / "Map_001.wz"


def test_listing_gives_a_directorys_images_and_subdirectories(
    client: ClientData,
) -> None:
    assert list(client.directory("Map/Map").directories) == ["Map0"]
    assert list(client.directory("Map/Map").images) == []
    assert list(client.directory("Map/Map/Map0").images) == [
        "000001000.img",
        "000002000.img",
    ]
    assert list(client.directory("Mob").directories) == ["_Canvas"]


def test_walk_yields_every_image_below_a_directory(client: ClientData) -> None:
    paths = sorted(image.path for image in client.root.walk())

    assert paths == [
        "Map/Effect.img",
        "Map/Inner/first.img",
        "Map/Inner/second.img",
        "Map/Map/Map0/000001000.img",
        "Map/Map/Map0/000002000.img",
        "Map/Physics.img",
    ]


def test_node_returns_the_node_without_following_links(client: ClientData) -> None:
    path = "Map/Map/Map0/000001000.img"

    assert client.node(f"{path}/info/bgm") == StringNode(
        name="bgm", value="Bgm00/GoPicnic"
    )
    assert client.node(f"{path}/stand/1") == UolNode(name="1", path="0")
    assert isinstance(client.node(path), PropertyNode)


@pytest.mark.parametrize(
    "path",
    [
        "Nowhere",
        "Map/Map/Map0/000009999.img",
        "Map/Map/Map0/000001000.img/info/nothing",
        "Map/Map/Map0/000001000.img/info/bgm/deeper",
    ],
)
def test_a_missing_path_raises_node_not_found(client: ClientData, path: str) -> None:
    with pytest.raises(NodeNotFound):
        client.node(path)


def test_node_not_found_inside_an_image_names_the_image_and_node(
    client: ClientData,
) -> None:
    with pytest.raises(NodeNotFound) as caught:
        client.node("Map/Map/Map0/000001000.img/info/nothing")

    assert caught.value.image == "000001000.img"
    assert caught.value.node == "info/nothing"
    assert isinstance(caught.value, LookupError)


def test_image_and_directory_reject_the_wrong_kind_of_path(client: ClientData) -> None:
    with pytest.raises(NodeNotFound):
        client.image("Map/Map")
    with pytest.raises(NodeNotFound):
        client.image("Map/Physics.img/walkForce")
    with pytest.raises(NodeNotFound):
        client.directory("Map/Physics.img")


def test_a_missing_data_folder_raises(tmp_path: Path) -> None:
    with pytest.raises(NotADirectoryError):
        ClientData(tmp_path / "nowhere")


# --- links -----------------------------------------------------------------

STAND = "Map/Map/Map0/000001000.img/stand"
WALK = "Map/Map/Map0/000001000.img/walk"


@pytest.mark.parametrize(
    ("path", "target"),
    [
        (f"{STAND}/1", f"{STAND}/0"),
        (f"{STAND}/move/again", f"{STAND}/0"),
        (f"{WALK}/frames/first", f"{WALK}/move/0"),
        (f"{WALK}/chain", f"{WALK}/move/0"),
        (f"{WALK}/elsewhere", "Map/Map/Map0/000002000.img/info/bgm"),
        (f"{WALK}/up", "Map/Physics.img/walkForce"),
    ],
)
def test_resolve_follows_a_link_relative_to_its_parent(
    client: ClientData, path: str, target: str
) -> None:
    assert client.resolve(path) == client.node(target)


def test_resolve_follows_links_in_the_middle_of_a_path(client: ClientData) -> None:
    assert client.resolve(f"{WALK}/alias/0/delay") == IntNode(name="delay", value=180)
    assert client.resolve(f"{STAND}/1/delay") == IntNode(name="delay", value=100)


def test_resolve_without_links_is_node(client: ClientData) -> None:
    path = "Map/Map/Map0/000001000.img/info/bgm"

    assert client.resolve(path) == client.node(path)


def test_a_link_to_nothing_raises_node_not_found(client: ClientData) -> None:
    with pytest.raises(NodeNotFound):
        client.resolve(f"{WALK}/nowhere")


def test_a_link_climbing_above_the_top_raises_node_not_found(
    client: ClientData,
) -> None:
    with pytest.raises(NodeNotFound, match="climbs above the top"):
        client.resolve(f"{WALK}/too far")


def test_links_that_loop_raise(client: ClientData) -> None:
    with pytest.raises(CorruptArchive, match="links"):
        client.resolve(f"{WALK}/loop a")


# --- malformed trees -------------------------------------------------------


def test_an_image_in_two_parts_raises(tmp_path: Path) -> None:
    root = tmp_path / "Data"
    w.write_tree(
        root / "Etc",
        stub=[],
        parts=[[w.Img("Same.img", [])], [w.Img("Same.img", [])]],
    )

    with pytest.raises(CorruptArchive, match="also in Etc_000.wz") as caught:
        _ = ClientData(root).directory("Etc").images

    assert caught.value.image == "Same.img"


def test_a_part_the_ini_lists_but_that_is_missing_raises(tmp_path: Path) -> None:
    root = tmp_path / "Data"
    w.write_tree(root / "Etc", stub=[], parts=[[w.Img("a.img", [])]])
    (root / "Etc" / "Etc.ini").write_text("LastWzIndex|1\n")

    with pytest.raises(CorruptArchive, match="Etc_001.wz"):
        _ = ClientData(root).directory("Etc").images


@pytest.mark.parametrize("text", ["LastWzIndex|x\n", "Something|0\n", "garbage\n"])
def test_an_unreadable_ini_raises(tmp_path: Path, text: str) -> None:
    root = tmp_path / "Data"
    w.write_tree(root / "Etc", stub=[], parts=[[w.Img("a.img", [])]])
    (root / "Etc" / "Etc.ini").write_text(text)

    with pytest.raises(CorruptArchive) as caught:
        _ = ClientData(root).directory("Etc").images

    assert caught.value.archive == str(root / "Etc" / "Etc.ini")


def test_a_corrupt_image_raises_through_the_namespace(tmp_path: Path) -> None:
    root = tmp_path / "Data"
    w.write_tree(
        root / "Etc", stub=[], parts=[[w.Img("bad.img", [w.Prop("p", [w.Bad("x")])])]]
    )

    with pytest.raises(CorruptArchive) as caught:
        ClientData(root).node("Etc/bad.img/p")

    assert caught.value.archive == str(root / "Etc" / "Etc_000.wz")
    assert caught.value.image == "bad.img"
    assert caught.value.node == "p/x"


# --- packs -----------------------------------------------------------------
#
#     Data/
#       Mob/          Mob.wz (stub: _Canvas), Mob.ini (no parts)
#       Skill/        Skill.wz (stub: MobSkill), Skill.ini (no parts)
#         MobSkill/   MobSkill.wz (empty stub), MobSkill.ini (no parts)
#       Packs/        Mob_00000.ms, Skill_00000.ms, digest.md5

MOB_PACK: list[w.Img | w.Blob] = [
    w.Img(
        "Mob/0000001.img",
        [w.Prop("info", [w.Int("level", 1), w.Uol("same", "../../0000002.img/info")])],
    ),
    w.Img("Mob/0000002.img", [w.Prop("info", [w.Int("level", 2)])]),
    w.Blob("Mob/pack_ignore.txt", b"ignore\r\n"),
]
SKILL_PACK: list[w.Img | w.Blob] = [
    w.Img("Skill/110.img", [w.Prop("skill", [w.Int("maxLevel", 20)])]),
    w.Img("Skill/MobSkill/200.img", [w.Prop("level", [w.Int("1", 5)])]),
    w.Img("Skill/Extra/1.img", [w.Int("only", 1)]),
    w.Blob("Skill/pack_ignore.txt", b"ignore\r\n"),
]


def _classic(root: Path, *, mob_stub: list[w.Dir | w.Img] | None = None) -> Path:
    w.write_tree(root / "Mob", stub=mob_stub or [w.Dir("_Canvas")])
    w.write_tree(root / "Skill", stub=[w.Dir("MobSkill")])
    w.write_tree(root / "Skill" / "MobSkill", stub=[])
    w.write_pack(root / "Packs" / "Mob_00000.ms", MOB_PACK)
    w.write_pack(root / "Packs" / "Skill_00000.ms", SKILL_PACK)
    (root / "Packs" / "digest.md5").write_text("not a pack\n")
    return root


@pytest.fixture
def classic(tmp_path: Path) -> ClientData:
    return ClientData(_classic(tmp_path / "Data"))


def test_pack_images_are_listed_under_their_tree(classic: ClientData) -> None:
    assert list(classic.root.directories) == ["Mob", "Skill"]
    assert list(classic.directory("Mob").images) == ["0000001.img", "0000002.img"]
    assert list(classic.directory("Mob").directories) == ["_Canvas"]
    assert list(classic.directory("Skill").images) == ["110.img"]
    assert list(classic.directory("Skill/MobSkill").images) == ["200.img"]


def test_a_directory_only_a_pack_has_is_listed(classic: ClientData) -> None:
    assert sorted(classic.directory("Skill").directories) == ["Extra", "MobSkill"]
    assert list(classic.directory("Skill/Extra").images) == ["1.img"]


def test_a_pack_image_resolves_to_its_pack(classic: ClientData) -> None:
    image = classic.image("Skill/MobSkill/200.img")

    assert image.archive == classic.data / "Packs" / "Skill_00000.ms"
    assert image.name == "200.img"
    assert image.path == "Skill/MobSkill/200.img"
    assert classic.node("Skill/110.img/skill/maxLevel") == IntNode(
        name="maxLevel", value=20
    )
    assert classic.node("Skill/MobSkill/200.img/level/1") == IntNode(name="1", value=5)


def test_a_pack_image_reads_decrypted(classic: ClientData) -> None:
    image = classic.image("Mob/0000002.img")
    written = MOB_PACK[1]
    assert isinstance(written, w.Img)

    assert image.read() == w.image_bytes(written.children)[0]
    assert isinstance(classic.image("Mob/0000001.img").entry, PackEntry)


def test_links_resolve_between_pack_images(classic: ClientData) -> None:
    assert classic.resolve("Mob/0000001.img/info/same/level") == IntNode(
        name="level", value=2
    )


def test_walk_reaches_pack_images(classic: ClientData) -> None:
    assert sorted(image.path for image in classic.root.walk()) == [
        "Mob/0000001.img",
        "Mob/0000002.img",
        "Skill/110.img",
        "Skill/Extra/1.img",
        "Skill/MobSkill/200.img",
    ]


def test_entries_that_are_not_images_are_skipped(classic: ClientData) -> None:
    assert classic.skipped == ["Mob/pack_ignore.txt", "Skill/pack_ignore.txt"]
    assert "pack_ignore.txt" not in classic.directory("Mob").images
    with pytest.raises(NodeNotFound):
        classic.image("Mob/pack_ignore.txt")


def test_an_image_in_a_pack_and_in_a_part_raises_naming_both(tmp_path: Path) -> None:
    root = _classic(tmp_path / "Data")
    w.write_tree(
        root / "Mob",
        stub=[w.Dir("_Canvas")],
        parts=[[w.Img("0000002.img", [w.Int("wz", 1)])]],
    )

    with pytest.raises(CorruptArchive) as caught:
        _ = ClientData(root).directory("Mob").images

    assert caught.value.archive == str(root / "Packs" / "Mob_00000.ms")
    assert caught.value.image == "Mob/0000002.img"
    assert str(root / "Mob" / "Mob_000.wz") in str(caught.value)


def test_an_image_in_a_pack_and_in_a_stub_raises_naming_both(tmp_path: Path) -> None:
    root = _classic(
        tmp_path / "Data",
        mob_stub=[w.Dir("_Canvas"), w.Img("0000002.img", [w.Int("stub", 1)])],
    )

    with pytest.raises(CorruptArchive) as caught:
        _ = ClientData(root).directory("Mob").images

    assert caught.value.archive == str(root / "Packs" / "Mob_00000.ms")
    assert caught.value.image == "Mob/0000002.img"
    assert str(root / "Mob" / "Mob.wz") in str(caught.value)


def test_an_image_in_two_packs_raises(tmp_path: Path) -> None:
    root = _classic(tmp_path / "Data")
    w.write_pack(root / "Packs" / "Mob_00001.ms", [MOB_PACK[0]])

    with pytest.raises(CorruptArchive, match="also in") as caught:
        _ = ClientData(root).root.directories

    assert caught.value.archive == str(root / "Packs" / "Mob_00001.ms")
    assert caught.value.image == "Mob/0000001.img"


def test_a_pack_that_is_not_v2_raises_when_the_namespace_is_listed(
    tmp_path: Path,
) -> None:
    root = _classic(tmp_path / "Data")
    w.write_pack(root / "Packs" / "Mob_00000.ms", MOB_PACK, version=2)

    with pytest.raises(UnsupportedFormat, match="decodes to 2,") as caught:
        _ = ClientData(root).root.directories

    assert caught.value.archive == str(root / "Packs" / "Mob_00000.ms")


def test_a_top_level_directory_only_a_pack_has_is_listed(tmp_path: Path) -> None:
    root = _classic(tmp_path / "Data")
    w.write_pack(root / "Packs" / "Etc_00000.ms", [w.Img("Etc/Only.img", [])])
    client = ClientData(root)

    assert sorted(client.root.directories) == ["Etc", "Mob", "Skill"]
    assert client.image("Etc/Only.img").archive == root / "Packs" / "Etc_00000.ms"
