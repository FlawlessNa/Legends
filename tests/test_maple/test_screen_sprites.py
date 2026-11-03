"""
The readers' sprite set on a stubbed store: a hand-built extraction in a
temporary root, and a client folder the test fills or leaves empty.
"""

import functools
import json
import shutil
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Self

import numpy as np
import pytest

from botting.core import DecisionMaker
from game_data.catalogue.model import Ref, SkillData
from game_data.extraction import Manifest, Store
from maple.bots import maple_bot
from maple.bots.maple_bot import MapleBot
from maple.screen import client
from maple.screen import sprites as sprites_module
from maple.screen.sprites import (
    FRAME_CHECK,
    GAUGE_LABEL,
    Declaration,
    Profile,
    StartupRefused,
    enabled_readers,
    job_line,
    load_reader_sprites,
    skill_icon_path,
)

BUILD = "0123456789abcdef"
LABEL = np.full((7, 5, 4), 255, dtype=np.uint8)
LABEL_NAME = "aa" * 32
ICON = np.full((4, 4, 4), 128, dtype=np.uint8)
ICON_NAME = "bb" * 32

STATUS_BAR = {
    "canvas:gaugeLabel": {"$type": "canvas", "image": LABEL_NAME, "w": 5, "h": 7},
    "gauge": {"vector:posNumberHp": {"$type": "vector", "x": -7, "y": 9}},
}
BUFF_ICONS = {
    "2301004": {
        "icon": {
            "$type": "canvas",
            "image": ICON_NAME,
            "w": 4,
            "h": 4,
            "origin": {"$type": "vector", "x": 0, "y": 4},
        }
    }
}
PROFILE = Profile(job="Cleric", game_map="Line1Area1")
STATUS = Declaration(
    "status bar",
    canvases=(GAUGE_LABEL,),
    vectors=("UI/StatusBar.img/gauge/vector:posNumberHp",),
)


def _buff_icons(profile: Profile) -> list[str]:
    return ["Skill/230.img/2301004/icon"] if profile.job == "Cleric" else []


BUFFS = Declaration("buffs", canvases=_buff_icons)


def build_store(root: Path) -> None:
    store = Store(root)
    folder = store.extraction(BUILD)
    folder.mkdir(parents=True)
    Manifest(
        build=BUILD,
        extractor_version=1,
        catalogue_schema_version=None,
        extracted_at=datetime(2026, 10, 31, tzinfo=UTC),
        archives=(),
        images=2,
        canvases=2,
        failures=(),
    ).write(folder)
    with closing(sqlite3.connect(folder / "raw.sqlite")) as db:
        db.execute(
            "CREATE TABLE images (path TEXT PRIMARY KEY, sha256 TEXT, tree TEXT)"
        )
        for path, tree in {
            "UI/StatusBar.img": STATUS_BAR,
            "Skill/230.img": BUFF_ICONS,
        }.items():
            db.execute("INSERT INTO images VALUES (?, '', ?)", (path, json.dumps(tree)))
        db.commit()
    store.images.write(LABEL_NAME, LABEL)
    store.images.write(ICON_NAME, ICON)


@pytest.fixture
def client_data(tmp_path: Path) -> Path:
    folder = tmp_path / "Data"
    folder.mkdir()
    return folder


@pytest.fixture
def config(tmp_path: Path, client_data: Path) -> Path:
    file = tmp_path / "game_data.ini"
    file.write_text(f"[Client]\nData = {client_data}\n", encoding="utf-8")
    return file


@pytest.fixture
def root(tmp_path: Path) -> Path:
    build_store(tmp_path / "store")
    return tmp_path / "store"


def test_it_loads_fixed_and_profile_dependent_sprites_once(
    root: Path, config: Path
) -> None:
    sprites = load_reader_sprites(
        [FRAME_CHECK, STATUS, BUFFS], PROFILE, root, config=config
    )
    shutil.rmtree(root)  # nothing is read from the store after loading

    assert sprites.build == BUILD
    assert (sprites.canvas(GAUGE_LABEL).rgba == LABEL).all()
    assert sprites.canvas("Skill/230.img/2301004/icon").origin == (0, 4)
    assert sprites.vector("UI/StatusBar.img/gauge/vector:posNumberHp") == (-7, 9)
    with pytest.raises(KeyError, match="enabled reader"):
        sprites.canvas("UI/StatusBar.img/gauge")


def test_no_reader_needs_no_store(tmp_path: Path) -> None:
    sprites = load_reader_sprites([], PROFILE, tmp_path, config=tmp_path / "none.ini")

    assert sprites.build is None
    assert sprites.canvases == {}


def test_a_missing_config_is_refused_saying_how_to_create_it(
    root: Path, tmp_path: Path
) -> None:
    with pytest.raises(
        StartupRefused,
        match=r"game_data\.ini is missing.*copy configs/game_data\.example\.ini",
    ):
        load_reader_sprites(
            [FRAME_CHECK], PROFILE, root, config=tmp_path / "game_data.ini"
        )


def test_a_config_without_a_client_is_refused(root: Path, tmp_path: Path) -> None:
    file = tmp_path / "game_data.ini"
    file.write_text("[Client]\nData =\n", encoding="utf-8")

    with pytest.raises(StartupRefused, match=r"doesn't set \[Client\] Data"):
        load_reader_sprites([FRAME_CHECK], PROFILE, root, config=file)


def test_a_missing_store_is_refused_saying_to_extract(
    tmp_path: Path, config: Path
) -> None:
    with pytest.raises(
        StartupRefused, match=r"has no extraction: run `python -m game_data extract`"
    ):
        load_reader_sprites([FRAME_CHECK], PROFILE, tmp_path / "empty", config=config)


def test_a_stale_store_is_refused_naming_what_changed(
    root: Path, config: Path, client_data: Path
) -> None:
    (client_data / "UI.wz").write_bytes(b"patched")

    with pytest.raises(
        StartupRefused,
        match=rf"stale.*build {BUILD} \(UI\.wz\).*python -m game_data extract",
    ):
        load_reader_sprites([FRAME_CHECK], PROFILE, root, config=config)


def test_a_declared_sprite_that_doesnt_exist_is_refused_naming_it(
    root: Path, config: Path
) -> None:
    broken = Declaration("minimap", canvases=("UI/MiniMap.img/MaxMap/nw",))

    with pytest.raises(
        StartupRefused, match=r"minimap reader .*UI/MiniMap\.img/MaxMap/nw"
    ):
        load_reader_sprites([FRAME_CHECK, broken], PROFILE, root, config=config)


def test_a_declared_vector_that_doesnt_exist_is_refused_naming_it(
    root: Path, config: Path
) -> None:
    broken = Declaration(
        "status bar", vectors=("UI/StatusBar.img/gauge/vector:posNumberMp",)
    )

    with pytest.raises(StartupRefused, match=r"status bar reader .*vector:posNumberMp"):
        load_reader_sprites([broken], PROFILE, root, config=config)


class _Reads(DecisionMaker):
    screen_readers = (STATUS,)

    async def _decide(self) -> None: ...


class _AlsoReads(DecisionMaker):
    screen_readers = (STATUS, BUFFS)

    async def _decide(self) -> None: ...


class _Blind(DecisionMaker):
    async def _decide(self) -> None: ...


def test_enabled_readers_are_those_the_decision_makers_name_with_the_frame_check() -> (
    None
):
    assert enabled_readers([_Reads, _Blind, _AlsoReads]) == [FRAME_CHECK, STATUS, BUFFS]
    assert enabled_readers([_Blind]) == []


class _Bot(MapleBot):
    def _decision_makers(self) -> list[type[DecisionMaker]]:
        return [_Reads, _Blind]


def test_child_init_refuses_before_creating_any_attribute(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, root: Path
) -> None:
    monkeypatch.setattr(client, "find_window", lambda *_: 4242)
    monkeypatch.setattr(
        maple_bot,
        "load_reader_sprites",
        functools.partial(load_reader_sprites, root=root, config=tmp_path / "none.ini"),
    )
    created: list[str] = []
    monkeypatch.setattr(
        maple_bot.InGameDetectionVisuals,
        "register_models",
        lambda *_: created.append("models"),
    )
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        game_map="Line1Area1",
        character_class="Bishop",
        models_path={},
    )

    with pytest.raises(StartupRefused, match="none.ini is missing"):
        bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert created == []


def test_child_init_keeps_the_loaded_sprites_and_a_frame_check(
    monkeypatch: pytest.MonkeyPatch, root: Path, config: Path
) -> None:
    monkeypatch.setattr(client, "find_window", lambda *_: 4242)
    monkeypatch.setattr(
        maple_bot,
        "load_reader_sprites",
        functools.partial(load_reader_sprites, root=root, config=config),
    )
    monkeypatch.setattr(
        maple_bot.InGameDetectionVisuals, "register_models", lambda *_: None
    )
    monkeypatch.setattr(
        maple_bot.InGameDetectionVisuals, "register_cache_id", lambda *_: None
    )
    bot = _Bot(
        "Someone",
        {},  # pyright: ignore[reportArgumentType] - metadata is never read here
        game_map="Line1Area1",
        character_class="Bishop",
        models_path={},
    )

    bot.child_init(None, None)  # pyright: ignore[reportArgumentType] - neither is used before start()

    assert bot.data is not None
    assert bot.data.reader_sprites.build == BUILD
    assert bot.data.frame_check.locator.anchor.sprite.path == GAUGE_LABEL


# Skill icons: found in the catalogue by name and the profile's job.


class _Catalogue:
    """The `Catalogue` calls `skill_icon_path` makes, over a few skills."""

    def __init__(self, skills: dict[int, tuple[str, int]]) -> None:
        self.skills = skills

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None: ...

    def search(self, text: str, kind: str | None = None) -> list[Ref]:
        assert kind == "skill"
        return [
            Ref("skill", id_, name)
            for id_, (name, _) in self.skills.items()
            if text.casefold() in name.casefold()
        ]

    def skill(self, name_or_id: str | int) -> SkillData:
        name, job = self.skills[int(name_or_id)]
        return SkillData(int(name_or_id), job, name, None, None, 20, (), None, ())


CATALOGUE = _Catalogue(
    {
        1001: ("Recovery", 0),
        2001000: ("Magic Guard", 200),
        2301003: ("Bless", 230),
        4101001: ("Haste", 410),
        4201001: ("Haste", 420),
        2000000: ("Improved MP Recovery", 200),
    }
)


@pytest.mark.parametrize(
    ("job", "line"),
    [
        ("Beginner", {0}),
        ("Magician", {0, 200}),
        ("Cleric", {0, 200, 230}),
        ("bishop", {0, 200, 230, 231, 232}),
        ("Hermit", {0, 400, 410, 411}),
        ("Wizardfirepoison", {0, 200, 210}),
    ],
)
def test_a_jobs_line_is_it_and_every_job_before_it(job: str, line: set[int]) -> None:
    assert job_line(job) == line


def test_an_unknown_job_has_no_line() -> None:
    with pytest.raises(LookupError, match="no job id for 'Hero'"):
        job_line("Hero")


@pytest.mark.parametrize(
    ("name", "job", "path"),
    [
        ("Bless", "Priest", "Skill/230.img/skill/2301003/icon"),
        ("magic guard", "Cleric", "Skill/200.img/skill/2001000/icon"),
        ("Recovery", "Magician", "Skill/000.img/skill/0001001/icon"),
        ("Haste", "Assassin", "Skill/410.img/skill/4101001/icon"),
        ("Haste", "Bandit", "Skill/420.img/skill/4201001/icon"),
    ],
)
def test_a_skill_icon_is_the_jobs_skill_of_that_whole_name(
    name: str, job: str, path: str
) -> None:
    assert skill_icon_path(CATALOGUE, name, job) == path


def test_a_skill_another_job_has_isnt_found() -> None:
    with pytest.raises(LookupError, match=r"'Bless'.*has none"):
        skill_icon_path(CATALOGUE, "Bless", "Assassin")


ICON_PATH = "Skill/230.img/skill/2301003/icon"
STORE_ICONS = {
    "skill": {
        "2301003": {
            "icon": {
                "$type": "canvas",
                "image": ICON_NAME,
                "w": 4,
                "h": 4,
                "origin": {"$type": "vector", "x": 0, "y": 4},
            }
        }
    }
}
NAMED_BUFFS = Declaration("buffs", skill_icons=lambda profile: profile.buffs)


@pytest.fixture
def icon_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "icon_store"
    build_store(root)
    db = sqlite3.connect(Store(root).extraction(BUILD) / "raw.sqlite")
    with closing(db):
        db.execute(
            "UPDATE images SET tree = ? WHERE path = 'Skill/230.img'",
            (json.dumps(STORE_ICONS),),
        )
        db.commit()
    monkeypatch.setattr(sprites_module.Catalogue, "open", lambda *_: CATALOGUE)
    return root


def test_declared_skill_icons_are_loaded_by_skill_name(
    icon_root: Path, config: Path
) -> None:
    profile = Profile(job="Priest", game_map="x", buffs=("Bless",))

    sprites = load_reader_sprites([NAMED_BUFFS], profile, icon_root, config=config)

    assert sprites.skill_icon("Bless").path == ICON_PATH
    assert sprites.skill_icon("Bless").origin == (0, 4)
    with pytest.raises(KeyError, match="'Haste' icon"):
        sprites.skill_icon("Haste")


def test_a_skill_the_job_doesnt_have_is_refused_naming_it(
    icon_root: Path, config: Path
) -> None:
    profile = Profile(job="Assassin", game_map="x", buffs=("Bless",))

    with pytest.raises(
        StartupRefused,
        match=r"buffs reader can't find the 'Bless' icon.*character_class",
    ):
        load_reader_sprites([NAMED_BUFFS], profile, icon_root, config=config)


def test_no_skill_named_opens_no_catalogue(
    root: Path, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*_: object) -> None:
        raise AssertionError("the catalogue was opened")

    monkeypatch.setattr(sprites_module.Catalogue, "open", refuse)

    assert (
        load_reader_sprites([NAMED_BUFFS], PROFILE, root, config=config).skill_icons
        == {}
    )
