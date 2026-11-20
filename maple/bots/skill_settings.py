"""
The profile's buff settings: `buffs`, the buffs `SoloRebuff` keeps up, by skill
name (spec #631 § 7).

The launcher profile passes `settings` to the bot verbatim
(`maple/launchers/profile.py`), so the bot is what reads them. A name is checked
against the character's skills when `SoloRebuff` is set up, since the skills
are built in the Bot's process (`SkillsProvider`).
"""

from __future__ import annotations

from maple.launchers.profile import ProfileError


def refuse_buff_lists(included_buffs: object, excluded_buffs: object) -> None:
    """
    `included_buffs` and `excluded_buffs` edited the buffs the hand-written skill
    tables marked "used by default". The tables are gone (#635): the skills come
    from the client's files, and the profile lists the buffs to keep up.

    :raises ProfileError: Either is set.
    """
    for setting, value in (
        ("included_buffs", included_buffs),
        ("excluded_buffs", excluded_buffs),
    ):
        if value is None:
            continue
        raise ProfileError(
            f"`{setting}: {value}` is retired with the hand-written skill tables "
            "(#635): no buff is used by default any more. List every buff to keep "
            "up in `buffs`, by its name in the Skill Keys, such as "
            "`buffs: [Iron Body]`."
        )


def buff_names(buffs: object) -> tuple[str, ...]:
    """
    The profile's `buffs`: the names of the buffs to keep up; none when unset.

    :raises ProfileError: `buffs` isn't a list of names.
    """
    if buffs is None:
        return ()
    if not isinstance(buffs, list) or not all(isinstance(b, str) for b in buffs):
        raise ProfileError(
            f"`buffs: {buffs}` must be a list of skill names, such as "
            "`buffs: [Iron Body]`."
        )
    return tuple(buffs)
