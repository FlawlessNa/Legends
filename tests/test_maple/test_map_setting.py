"""
The profile's `map` setting, resolved by the bot through the catalogue.

The catalogue is the synthetic client of `test_catalogue`: map 100 is
"Victoria Road: Henesys", and 200 and 201 are both "Mushroom Town".
"""

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from game_data.catalogue import Catalogue, build_catalogue
from game_data.extraction import extract
from maple.bots.map_setting import is_auto, resolve_map_id
from maple.launchers.profile import ProfileError
from tests.test_game_data.test_catalogue import write_map_client

HENESYS = 100


@pytest.fixture(autouse=True)
def store(tmp_path: Path, mocker: MockerFixture) -> None:
    root = tmp_path / "store"
    build = extract(
        write_map_client(tmp_path / "Data"), root, catalogue=build_catalogue
    ).manifest.build
    mocker.patch.object(
        Catalogue, "latest", classmethod(lambda cls: Catalogue.open(build, root))
    )


def _map_file(mocker: MockerFixture, map_id: int | None) -> None:
    file = mocker.Mock(map_id=map_id)
    mocker.patch(
        "maple.bots.map_setting.MinimapEditsManager.from_json", return_value=file
    )


def test_a_game_map_name_resolves_to_its_id() -> None:
    assert resolve_map_id("Victoria Road: Henesys", "Line1Area1") == HENESYS


def test_a_map_id_is_accepted() -> None:
    assert resolve_map_id(HENESYS, "Line1Area1") == HENESYS
    assert resolve_map_id(str(HENESYS), "Line1Area1") == HENESYS


def test_an_ambiguous_name_is_a_profile_error_listing_the_ids() -> None:
    with pytest.raises(ProfileError, match=r"200.*201|201.*200"):
        resolve_map_id("Mushroom Town", "Line1Area1")


def test_an_unknown_name_is_a_profile_error() -> None:
    with pytest.raises(ProfileError, match="Nowhere"):
        resolve_map_id("Nowhere At All", "Line1Area1")


def test_an_unknown_id_is_a_profile_error() -> None:
    with pytest.raises(ProfileError):
        resolve_map_id(999999999, "Line1Area1")


@pytest.mark.parametrize("setting", ["auto", " AUTO "])
def test_auto_names_no_id_and_is_left_to_identification(setting: str) -> None:
    assert is_auto(setting)
    assert resolve_map_id(setting, "Line1Area1") is None


def test_auto_without_game_map_is_a_profile_error_saying_the_map_file_is_needed() -> (
    None
):
    with pytest.raises(ProfileError, match="game_map"):
        resolve_map_id("auto", None)


def test_a_name_or_an_id_is_not_auto() -> None:
    assert not is_auto("Victoria Road: Henesys")
    assert not is_auto(HENESYS)
    assert not is_auto(None)


def test_map_without_game_map_is_a_profile_error_saying_the_map_file_is_needed() -> (
    None
):
    with pytest.raises(ProfileError, match="game_map"):
        resolve_map_id("Victoria Road: Henesys", None)


def test_game_map_alone_still_works_and_names_no_id() -> None:
    assert resolve_map_id(None, "Line1Area1") is None


def test_neither_setting_is_a_profile_error_naming_map() -> None:
    with pytest.raises(ProfileError, match="`map`"):
        resolve_map_id(None, None)


def test_when_both_are_set_the_map_settings_id_wins(mocker: MockerFixture) -> None:
    _map_file(mocker, HENESYS)

    assert resolve_map_id("Victoria Road: Henesys", "Line1Area1") == HENESYS


def test_a_map_file_that_disagrees_is_a_profile_error(mocker: MockerFixture) -> None:
    _map_file(mocker, 101)

    with pytest.raises(ProfileError, match="101"):
        resolve_map_id("Victoria Road: Henesys", "Line1Area1")


def test_a_map_file_with_no_map_id_does_not_disagree(mocker: MockerFixture) -> None:
    _map_file(mocker, None)

    assert resolve_map_id(HENESYS, "Line1Area1") == HENESYS
