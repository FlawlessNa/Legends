"""
Skill images and the character's actions, as `skills`, `skill_levels` and
`actions` rows.

A job's skill image, `Skill/<job>.img`, holds `skill/<id>/` for each of its
skills:

- `level/<n>/`: that level's fields, such as `mpCon`, `time`, `lt`, `rb`,
  `mobCount`, `attackCount`, `range`, `cooltime`, `mad` or `x`. The common
  ones are `skill_levels` columns, and the rest go into its `other` JSON.
- `common/`: fields that hold at every level, such as a range or a cooldown.
  They're written into every level's row, as if each level had them. A
  skill with `common/maxLevel` and no `level` has that many levels, each of
  only the common fields. A field both in `common` and in a level is an error:
  which one wins isn't known.
- `action`: the character actions it plays, `action/<i>` or a single string.
- `info/type` and `icon`.

Images not named by a job, such as `Skill/Attacktype.img`, hold no player
skills and aren't read; nor is `Skill/MobSkill/`.

The character's actions are `Character/00002000.img`, the body: each child
but `info` is an action, and its numbered children are its frames, each with
a `delay` in milliseconds. A composite action's frames borrow another action's
pose, and some carry a negative delay; an action's duration sums the delays'
magnitudes (see `docs/agents/game-data.md`).
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Final

from game_data.extraction import Json

from .maps import Row
from .trees import Tree

SKILL_IMAGE: Final = re.compile(r"Skill/(?P<job>\d+)\.img")
ACTIONS_IMAGE: Final = "Character/00002000.img"

# The fields that are `skill_levels` columns, in their order; `lt` and `rb`
# are two columns each.
COLUMNS: Final = (
    "mpCon",
    "time",
    "lt",
    "rb",
    "mobCount",
    "attackCount",
    "range",
    "cooltime",
)
_VECTORS: Final = frozenset({"lt", "rb"})
MAX_LEVEL: Final = "maxLevel"


@dataclass(slots=True)
class SkillRows:
    """The rows read so far, by table."""

    skills: list[Row] = field(default_factory=list[Row])
    skill_levels: list[Row] = field(default_factory=list[Row])


def read_skills(
    trees: Mapping[int, Tree], names: Mapping[int, tuple[str | None, str | None]]
) -> SkillRows:
    """
    Every job's skills.

    :param trees: Each job's skill image, by the job.
    :param names: Each skill's name and description, from `String/Skill.img`.
    """
    rows = SkillRows()
    seen: dict[int, Tree] = {}
    for job, tree in sorted(trees.items()):
        for key, skill in (
            tree.expect("property").at("skill").expect("property").children()
        ):
            if not key.isdigit():
                raise skill.error("a skill whose name isn't an ID")
            skill_id = int(key)
            if skill_id in seen:
                raise skill.error(
                    f"it is skill {skill_id}, as is {seen[skill_id].image}"
                )
            seen[skill_id] = skill
            skill.expect("property")
            levels = _levels(skill)
            name, description = names.get(skill_id, (None, None))
            info = skill.get("info")
            icon = skill.get("icon")
            rows.skills.append(
                (
                    skill_id,
                    job,
                    name,
                    description,
                    None if info is None else info.optional_integer("type"),
                    len(levels),
                    json.dumps(_actions(skill)),
                    None if icon is None else icon.resolved().canvas_image(),
                )
            )
            rows.skill_levels += [
                (skill_id, level, *_columns(fields), _other(fields))
                for level, fields in levels
            ]
    return rows


def _actions(skill: Tree) -> list[str]:
    found = skill.get("action")
    if found is None:
        return []
    if found.type == "string":
        return [found.str_value()]
    return [action.str_value() for _, action in found.expect("property").children()]


def _levels(skill: Tree) -> list[tuple[int, dict[str, Tree]]]:
    """Each level's fields, the common ones included, by level."""
    common: dict[str, Tree] = {}
    found = skill.get("common")
    if found is not None:
        common = dict(found.expect("property").children())
    max_level = common.pop(MAX_LEVEL, None)
    levels: list[tuple[int, dict[str, Tree]]] = []
    level_tree = skill.get("level")
    if level_tree is not None:
        for key, level in level_tree.expect("property").children():
            if not key.isdigit():
                raise level.error("a level that isn't numbered")
            fields = dict(level.expect("property").children())
            clash = sorted(fields.keys() & common.keys())
            if clash:
                raise fields[clash[0]].error(f"common/{clash[0]} sets it too")
            levels.append((int(key), fields | common))
    if max_level is not None:
        count = max_level.int_value()
        if levels and count != len(levels):
            raise max_level.error(
                f"it says {count} levels, and there are {len(levels)}"
            )
        if not levels:
            levels = [(level, dict(common)) for level in range(1, count + 1)]
    return sorted(levels, key=lambda found: found[0])


def _columns(fields: Mapping[str, Tree]) -> list[int | None]:
    values: list[int | None] = []
    for name in COLUMNS:
        node = fields.get(name)
        if name in _VECTORS:
            values += (None, None) if node is None else node.resolved().vector()
        else:
            values.append(None if node is None else node.int_value())
    return values


def _other(fields: Mapping[str, Tree]) -> str:
    """The fields that aren't columns, as JSON."""
    return json.dumps(
        {name: plain(node) for name, node in fields.items() if name not in COLUMNS},
        ensure_ascii=False,
    )


def plain(node: Tree) -> Json:
    """
    A field's value as plain JSON: an integer for any integer type or a string
    of digits, a float for a float or a double, `{"x", "y"}` for a vector, and
    the raw layer's JSON for anything else, such as an animation.
    """
    match node.type:
        case "int" | "short" | "long":
            return node.int_value()
        case "string":
            text = node.str_value()
            return int(text) if re.fullmatch(r"-?\d+", text) else text
        case "float" | "double":
            return node.number_value()
        case "vector":
            x, y = node.vector()
            return {"x": x, "y": y}
        case _:
            return node.value


def read_actions(tree: Tree) -> list[Row]:
    """`Character/00002000.img`'s actions, one row per frame."""
    rows: list[Row] = []
    for action, node in tree.expect("property").children():
        if action == "info":
            continue
        frames: list[tuple[int, int | None]] = []
        for key, frame in node.expect("property").children():
            if not key.isdigit():
                raise frame.error("a frame that isn't numbered")
            frames.append(
                (
                    int(key),
                    frame.resolved().expect("property").optional_integer("delay"),
                )
            )
        delays = [abs(delay) for _, delay in frames if delay is not None]
        duration = sum(delays) if delays else None
        rows += [(action, frame, delay, duration) for frame, delay in frames]
    return rows
