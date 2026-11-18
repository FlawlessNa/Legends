"""
The mobs a map has, by the detection class names the models use, and whether
the profile's models cover them.

The mobs come from the map's spawns in the game data (`WorldMap.mobs`), not
from the profile (ADR 0004). A mob's detection class is its name in the
client's strings with its spaces and dots removed (`game_data.scenes`'s
`class_name`, the one place the rule lives): `Bubbling` stays `Bubbling`,
`Selkie Jr.` becomes `SelkieJr`, `Pac Pinky` becomes `PacPinky`. It is the
rule the shipped models' classes follow, the one `synth` names a model's
classes by, and the one `InGameDetectionVisuals` compares a model's classes
with. It is not the mob's id: MSCW numbers its mobs its own way (Bubbling is
mob 14).

On every map of the extraction this was written against, `map_mobs` gives
the classes `synth` trains a map's model on (`map_classes`), so a model
`synth` trained for a map covers it. `synth` leaves out a mob with no
sprite, which this doesn't; none was spawned.

Where the rule can fail:

- A model trained on a name the client doesn't use: a private server's
  rename, or a mob this client doesn't have. The shipped `Slimy`, `SelkieJr`,
  `PlatoonChronos` and `PacPinky` are such mobs: no MSCW map spawns them.
- Two mobs with one name share a class. MSCW has several (`Blue Mushroom` is
  mob 16 and mob 800015, an event map's): if they look different, one class
  is right for only one of them.
- Two names that differ only in spaces or dots would share a class too. No
  extraction so far has such a pair.
- A mob the client's strings don't name has no class, so no model covers it.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import cache

from game_data.catalogue import Spawn
from game_data.scenes import class_name
from maple.launchers.profile import ProfileError
from paths import ROOT

MANIFEST = os.path.join(ROOT, "models.manifest.json")
"""The shipped models, with the classes each detects."""

RECIPE = "recipe.json"
"""A model trained from a recipe (`synth`) keeps it beside `weights/`, with
its `classes`."""

ALL = "All"
"""The `models_path` key of the model that handles every class no other key
names, as `InGameDetectionVisuals` looks a class's model up."""


@dataclass(frozen=True, slots=True)
class MapMob:
    """
    A kind of mob a map spawns.

    :ivar name: Its name in the client's strings, or `mob <id>` when it has
        none.
    :ivar detection_class: The class a detection model names it by; `None`
        when the client names the mob nowhere.
    """

    name: str
    detection_class: str | None


def map_mobs(spawns: Iterable[Spawn]) -> tuple[MapMob, ...]:
    """
    The kinds of mob among `spawns`, one per detection class, in class order;
    unnamed mobs last, by id.

    NPCs are left out, and so are hidden spawns (the map's `hide`), which the
    map doesn't place: a script or an event does. Boss spawns, with their
    long respawn times, count like any other: the map has them.
    """
    named: dict[str, MapMob] = {}
    unnamed: dict[int, MapMob] = {}
    for spawn in spawns:
        if spawn.kind != "mob" or spawn.hidden:
            continue
        if spawn.name is None:
            unnamed.setdefault(spawn.id, MapMob(f"mob {spawn.id}", None))
            continue
        kind = class_name(spawn.name)
        named.setdefault(kind, MapMob(spawn.name, kind))
    return (
        *(named[kind] for kind in sorted(named)),
        *(unnamed[id_] for id_ in sorted(unnamed)),
    )


def _folder(path: str) -> str:
    """A `models_path` folder, as `InGameDetectionVisuals.register_models`
    resolves it: as given when it exists, else from the repo root."""
    resolved = path if os.path.exists(path) else os.path.join(ROOT, path)
    return os.path.normcase(os.path.abspath(resolved))


@cache
def _manifest_classes(manifest: str) -> dict[str, frozenset[str]]:
    """Each shipped model's folder, with its classes."""
    with open(manifest, encoding="utf-8") as fh:
        models = json.load(fh)["models"]
    return {
        _folder(os.path.dirname(os.path.dirname(model["dest"]))): frozenset(
            model["classes"]
        )
        for model in models
    }


def model_classes(path: str, manifest: str = MANIFEST) -> frozenset[str] | None:
    """
    The classes the model in folder `path` detects: its `recipe.json`'s when
    it has one, else `models.manifest.json`'s for the shipped model that
    downloads there. `None` when neither names them.
    """
    folder = _folder(path)
    recipe = os.path.join(folder, RECIPE)
    if os.path.isfile(recipe):
        with open(recipe, encoding="utf-8") as fh:
            return frozenset(json.load(fh)["classes"])
    return _manifest_classes(manifest).get(folder)


def check_detection(
    mobs: Sequence[MapMob],
    models_path: Mapping[str, str] | None,
    where: str,
    classes_of: Callable[[str], frozenset[str] | None] | None = None,
) -> None:
    """
    Refuse a start whose models don't detect every mob the map has.

    A mob is looked up as `InGameDetectionVisuals` does: in the model its
    class keys in `models_path`, else in the one keyed `All`. A map with no
    mobs passes.

    :param mobs: The map's mobs (`map_mobs`).
    :param models_path: The profile's `models_path`.
    :param where: The map, as the message names it.
    :param classes_of: The classes of the model in a folder; `model_classes`
        by default.
    :raises ProfileError: A mob no configured model detects. The message names
        those mobs, each configured model with its classes, the mobs they do
        cover, and what to do.
    """
    models = dict(models_path or {})
    read = classes_of or model_classes
    classes = {label: read(path) for label, path in models.items()}

    def covered(mob: MapMob) -> bool:
        kind = mob.detection_class
        if kind is None:
            return False
        label = kind if kind in models else ALL
        found = classes.get(label)
        return found is not None and kind in found

    missing = [mob for mob in mobs if not covered(mob)]
    if not missing:
        return
    found = [mob for mob in mobs if covered(mob)]
    lines = [
        f"{where} has mobs no detection model in the profile detects: "
        + ", ".join(_described(mob) for mob in missing)
        + "."
    ]
    if found:
        lines.append(
            "Its models detect only " + ", ".join(_described(m) for m in found) + "."
        )
    if models:
        lines.append("The profile's `models_path`:")
        lines.extend(
            f"  {label}: {path} -> {_classes(classes[label])}"
            for label, path in models.items()
        )
    else:
        lines.append("The profile has no `models_path`.")
    lines.append(
        "A mob is looked for with the model keyed by its class, else the one "
        f"keyed `{ALL}` (see models.manifest.json for the shipped models' "
        "classes, `python scripts/fetch_models.py` to download them). Train a "
        "model for the missing mobs and add it to `models_path`, or name a map "
        "whose mobs a model detects."
    )
    raise ProfileError("\n".join(lines))


def _described(mob: MapMob) -> str:
    if mob.detection_class is None:
        return f"{mob.name} (unnamed in the client's strings, so no class)"
    if mob.detection_class == mob.name:
        return mob.name
    return f"{mob.name} (class {mob.detection_class})"


def _classes(classes: frozenset[str] | None) -> str:
    if classes is None:
        return (
            f"classes unknown: not in models.manifest.json, and no {RECIPE} "
            "beside its weights"
        )
    return ", ".join(sorted(classes))
