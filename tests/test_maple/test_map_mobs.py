"""
The mobs a map has, by detection class (#548), and the refusal of a start no
model covers: on synthetic `WorldMap`s, and on the local store's extraction
(`client_files`).
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from game_data.catalogue import Catalogue, Spawn
from game_data.config import STORE
from game_data.scenes import class_name
from maple.bots.map_mobs import (
    MANIFEST,
    MapMob,
    check_detection,
    map_mobs,
    model_classes,
)
from maple.launchers.profile import ProfileError
from maple.model.world import WorldMap
from tests.test_maple.movement_lab.fixture_maps import jump_gap

#: The shipped models' classes that name no mob of the MSCW client: they were
#: trained on mobs of a later client. They can't map, and a map never asks
#: for them.
NOT_IN_THE_CLIENT = {"Slimy", "SelkieJr", "PlatoonChronos", "PacPinky"}

#: The shipped models' classes that aren't mobs.
NOT_MOBS = {"Character"}


def _spawn(
    name: str | None, id_: int = 1, kind: str = "mob", *, hidden: bool = False
) -> Spawn:
    return Spawn(kind, id_, name, 0, 0, 1, -50, 50, None, False, hidden)


def _mob(name: str) -> MapMob:
    return MapMob(name, class_name(name))


# --- The mapping rule ---------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("Bubbling", "Bubbling"),
        ("Slimy", "Slimy"),
        ("Selkie Jr.", "SelkieJr"),
        ("Platoon Chronos", "PlatoonChronos"),
        ("Pac Pinky", "PacPinky"),
    ],
)
def test_a_mobs_class_is_its_name_without_spaces_and_dots(name: str, kind: str) -> None:
    """The shipped models' mobs, by their names in the client they come from."""
    assert class_name(name) == kind


def test_the_maps_mobs_come_from_its_mob_spawns() -> None:
    """One per class, in class order: NPCs and hidden spawns left out, a mob
    placed twice once, and a mob the client names nowhere last, with no class."""
    spawns = (
        _spawn("Regular Cab", 1012000, "npc"),
        _spawn("Jr. Necki", 18),
        _spawn("Bubbling", 14),
        _spawn("Bubbling", 14),
        _spawn("Stirge", 17),
        _spawn("Stirge", 800020),
        _spawn("Mano", 700004, hidden=True),
        _spawn(None, 4242),
    )
    world = WorldMap.from_map_data(replace(jump_gap(), spawns=spawns))

    assert map_mobs(world.mobs) == (
        MapMob("Bubbling", "Bubbling"),
        MapMob("Jr. Necki", "JrNecki"),
        MapMob("Stirge", "Stirge"),
        MapMob("mob 4242", None),
    )


def test_a_map_without_mob_spawns_has_no_mobs() -> None:
    world = WorldMap.from_map_data(
        replace(jump_gap(), spawns=(_spawn("Regular Cab", 1012000, "npc"),))
    )

    assert world.mobs == ()
    assert map_mobs(world.mobs) == ()


# --- What a configured model detects -----------------------------------------


def test_a_shipped_models_classes_come_from_the_manifest() -> None:
    assert model_classes("data/models/production/global") == frozenset(
        {"Character", "Slimy", "SelkieJr", "PlatoonChronos", "PacPinky", "Bubbling"}
    )
    assert model_classes("data/models/production/Bubbling_final") == frozenset(
        {"Bubbling", "Character"}
    )


def test_a_models_recipe_names_its_classes(tmp_path: Path) -> None:
    folder = tmp_path / "Octopus_synth"
    folder.mkdir()
    (folder / "recipe.json").write_text(json.dumps({"classes": ["Octopus"]}))

    assert model_classes(str(folder)) == frozenset({"Octopus"})


def test_a_model_neither_names_has_unknown_classes(tmp_path: Path) -> None:
    assert model_classes(str(tmp_path)) is None


# --- The refusal ---------------------------------------------------------------

CLASSES = {
    "models/global": frozenset({"Character", "Bubbling", "Slimy"}),
    "models/bubbling": frozenset({"Character", "Bubbling"}),
    "models/octopus": frozenset({"Octopus"}),
}


def _check(mobs: list[MapMob], models_path: dict[str, str] | None) -> None:
    check_detection(mobs, models_path, "map 1 (Somewhere)", CLASSES.get)


def test_a_map_whose_mobs_a_model_detects_passes() -> None:
    _check([_mob("Bubbling"), _mob("Slimy")], {"All": "models/global"})


def test_a_map_with_no_mobs_passes() -> None:
    _check([], {"All": "models/global"})
    _check([], None)


def test_a_mob_no_model_detects_is_refused_naming_it_and_the_models() -> None:
    with pytest.raises(ProfileError) as refused:
        _check([_mob("Ribbon Pig")], {"All": "models/global"})

    message = str(refused.value)
    assert "map 1 (Somewhere)" in message
    assert "Ribbon Pig (class RibbonPig)" in message
    assert "All: models/global -> Bubbling, Character, Slimy" in message
    assert "detect only" not in message


def test_a_model_covering_some_mobs_is_refused_naming_the_missing_ones() -> None:
    with pytest.raises(ProfileError) as refused:
        _check([_mob("Bubbling"), _mob("Octopus")], {"All": "models/global"})

    message = str(refused.value)
    assert "detects: Octopus." in message
    assert "detect only Bubbling." in message


def test_a_mob_is_looked_for_in_the_model_its_class_keys() -> None:
    """As `InGameDetectionVisuals` looks it up: a model keyed by a class is the
    one for that class, even when `All`'s would detect it."""
    _check([_mob("Octopus")], {"Octopus": "models/octopus", "All": "models/global"})
    with pytest.raises(ProfileError, match="detects: Bubbling"):
        _check(
            [_mob("Bubbling")], {"Bubbling": "models/octopus", "All": "models/global"}
        )
    # Keyed by another class, a model is no model for this one.
    with pytest.raises(ProfileError, match="detects: Slimy"):
        _check([_mob("Slimy")], {"Bubbling": "models/global"})


def test_a_model_whose_classes_are_unknown_detects_nothing() -> None:
    with pytest.raises(ProfileError, match="classes unknown"):
        _check([_mob("Bubbling")], {"All": "models/elsewhere"})


def test_a_mob_the_client_names_nowhere_is_refused() -> None:
    with pytest.raises(ProfileError, match="mob 4242 \\(unnamed"):
        _check([MapMob("mob 4242", None)], {"All": "models/global"})


def test_no_models_path_detects_nothing() -> None:
    with pytest.raises(ProfileError, match="no `models_path`"):
        _check([_mob("Bubbling")], None)


# --- On the local store's extraction ------------------------------------------


@pytest.mark.client_files
def test_the_shipped_models_mobs_map_to_the_clients() -> None:
    """Every mob class a shipped model detects is the class of a mob the
    client names, but those trained on another client's mobs."""
    if not STORE.exists():
        pytest.skip(f"no game data store at {STORE}")
    with open(MANIFEST, encoding="utf-8") as fh:
        shipped = {c for model in json.load(fh)["models"] for c in model["classes"]}
    with Catalogue.latest(STORE) as cat:
        names = cat._all("SELECT name FROM strings WHERE kind = 'mob'")  # pyright: ignore[reportPrivateUsage] - a reading of the store, not an API
    client = {class_name(str(name)) for (name,) in names if name}

    assert shipped - NOT_MOBS - NOT_IN_THE_CLIENT <= client
    assert not NOT_IN_THE_CLIENT & client, "a mob listed as not in the client is"


@pytest.mark.client_files
def test_line_1_area_1_has_bubblings_which_the_global_model_detects() -> None:
    """Kerning City Subway: Line 1 <Area 1>, the training map, spawns only
    Bubblings."""
    if not STORE.exists():
        pytest.skip(f"no game data store at {STORE}")
    mobs = map_mobs(WorldMap.load(10003061, root=STORE).mobs)

    assert mobs == (MapMob("Bubbling", "Bubbling"),)
    check_detection(mobs, {"All": "data/models/production/global"}, "map 10003061")


@pytest.mark.client_files
def test_ellinia_has_no_mobs() -> None:
    if not STORE.exists():
        pytest.skip(f"no game data store at {STORE}")

    assert map_mobs(WorldMap.load(10002000, root=STORE).mobs) == ()
