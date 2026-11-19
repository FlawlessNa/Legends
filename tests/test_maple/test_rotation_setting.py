"""
The profile's `rotation` setting (`maple/decision_makers/rotation_setting.py`):
which destination source the rotation heads for, read once in Main Process and
again by the Destination Provider (#577).
"""

import ast
from pathlib import Path

import pytest

from maple.decision_makers import rotation_setting
from maple.decision_makers.rotation_setting import ROTATIONS, rotation_name
from maple.launchers.profile import ProfileError


def test_the_rotations_are_random_smart_and_the_hunting_area() -> None:
    assert ROTATIONS == ("random", "smart", "hunting_area")


@pytest.mark.parametrize(
    ("settings", "expected"),
    [
        ({}, "random"),
        ({"smart_rotation_enabled": False}, "random"),
        ({"smart_rotation_enabled": True}, "smart"),
        # A setting left empty in the YAML is not given.
        ({"rotation": None, "smart_rotation_enabled": True}, "smart"),
        ({"rotation": "random", "smart_rotation_enabled": None}, "random"),
    ],
    ids=["neither", "smart-off", "smart-on", "empty-rotation", "empty-smart"],
)
def test_with_no_rotation_the_rotation_is_todays(
    settings: dict[str, object], expected: str
) -> None:
    assert rotation_name(settings) == expected


@pytest.mark.parametrize("name", ROTATIONS)
def test_a_named_rotation_is_that_one(name: str) -> None:
    assert rotation_name({"rotation": name}) == name


def test_the_hunting_area_rotation_may_name_its_area() -> None:
    settings = {"rotation": "hunting_area", "hunting_area": "right_corner"}

    assert rotation_name(settings) == "hunting_area"


@pytest.mark.parametrize("smart", [True, False])
@pytest.mark.parametrize("name", ROTATIONS)
def test_rotation_with_smart_rotation_enabled_is_refused(
    name: str, smart: bool
) -> None:
    """The rotation is named once, whatever the old setting's value."""
    settings = {"rotation": name, "smart_rotation_enabled": smart}

    with pytest.raises(ProfileError, match=r"`rotation: .*`smart_rotation_enabled"):
        rotation_name(settings)


@pytest.mark.parametrize(
    "settings",
    [
        {"hunting_area": "right_corner"},
        {"hunting_area": "right_corner", "rotation": "random"},
        {"hunting_area": "right_corner", "rotation": "smart"},
        {"hunting_area": "right_corner", "smart_rotation_enabled": True},
    ],
    ids=["no-rotation", "random", "smart", "smart-enabled"],
)
def test_a_hunting_area_without_its_rotation_is_refused(
    settings: dict[str, object],
) -> None:
    with pytest.raises(ProfileError, match=r"`hunting_area: right_corner`"):
        rotation_name(settings)


@pytest.mark.parametrize("unknown", ["spiral", "Random", 3])
def test_an_unknown_rotation_is_refused_listing_the_rotations(unknown: object) -> None:
    with pytest.raises(ProfileError, match=rf"`rotation: {unknown}`") as refused:
        rotation_name({"rotation": unknown})

    assert all(name in str(refused.value) for name in ROTATIONS)


def test_the_setting_imports_neither_the_bots_nor_the_providers() -> None:
    """
    `maple/bots` imports `maple.decision_makers`, and the Destination Provider
    imports this module: either import here would be a cycle.
    """
    tree = ast.parse(Path(rotation_setting.__file__).read_text(encoding="utf-8"))
    imported = [
        *(
            "." * node.level + (node.module or "")
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        ),
        *(
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        ),
    ]

    assert imported  # it does import: the check reads them
    assert not [
        name
        for name in imported
        # A relative import here would be from the decision makers' package.
        if name.startswith(("maple.bots", "maple.decision_makers.providers", "."))
    ]
