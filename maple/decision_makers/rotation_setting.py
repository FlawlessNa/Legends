"""
The profile's `rotation` setting: which destination source the rotation heads
for, by name (`maple/decision_makers/providers/destination.py`).

`rotation` replaced `smart_rotation_enabled` (#571): a profile with neither
rotates as it did before, `smart` when `smart_rotation_enabled` is true and
`random` otherwise.

`MapleBot.__init__` calls `rotation_name` in Main Process, so a bad setting ends
the launch with one line (`maple/launchers/run.py`), as a bad `map` does. The
Destination Provider calls it again and gets the same answer. This module reads
no registry: the names are `ROTATIONS`, and a test holds the registry to them.
"""

from collections.abc import Mapping

from maple.launchers.profile import ProfileError

#: Every rotation a profile can name, in the order the refusals list them.
ROTATIONS = ("random", "smart", "hunting_area")


def rotation_name(settings: Mapping[str, object]) -> str:
    """
    The rotation the profile's `settings` name: `rotation` when given; else
    `smart` when `smart_rotation_enabled` is true; else `random`. A setting
    left empty (YAML `null`) is not given.

    :raises ProfileError: `rotation` is given with `smart_rotation_enabled`
        (true or false: the rotation is named once), `rotation` is not one of
        `ROTATIONS`, or `hunting_area` is given with a rotation other than
        `hunting_area`. Each names the setting.
    """
    rotation = settings.get("rotation")
    smart = settings.get("smart_rotation_enabled")
    if rotation is not None and smart is not None:
        raise ProfileError(
            f"`rotation: {rotation}` and `smart_rotation_enabled: {smart}` both "
            "name the rotation: keep `rotation` and delete "
            "`smart_rotation_enabled`."
        )
    if rotation is None:
        name = "smart" if smart else "random"
    elif rotation in ROTATIONS:
        name = str(rotation)
    else:
        raise ProfileError(
            f"`rotation: {rotation}` is not a rotation: name one of "
            f"{', '.join(ROTATIONS)}."
        )
    area = settings.get("hunting_area")
    if area is not None and name != "hunting_area":
        raise ProfileError(
            f"`hunting_area: {area}` is set, and the rotation is {name}: set "
            "`rotation: hunting_area` to hunt it, or delete `hunting_area`."
        )
    return name
