"""
Load a launcher profile: the per-user answer to "which character, which map,
which model, which skills".

Profiles live in `profiles/<name>.yaml` and are gitignored, so everyone can
keep their own without fighting over the same file. `profiles/example.yaml` is
the committed template.

A profile is deliberately thin: `ign` and `bot` are the only keys this module
understands, and everything under `settings` is forwarded verbatim as keyword
arguments to the bot's constructor. Adding a new bot option therefore means
touching only the bot, never this loader.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

import yaml

from paths import ROOT

PROFILES_DIR = os.path.join(ROOT, "profiles")


class ProfileError(Exception):
    """A profile is missing, malformed, or points at something that isn't there."""


@dataclass
class BotSpec:
    """One bot to launch: which class, as whom, with what settings."""

    ign: str
    bot: str
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass
class Profile:
    """A whole launch: one main bot, plus any mules that ride along with it."""

    name: str
    main: BotSpec
    mules: list[BotSpec] = field(default_factory=list)


def available() -> list[str]:
    """Names of every profile on disk, example template included."""
    if not os.path.isdir(PROFILES_DIR):
        return []
    return sorted(
        os.path.splitext(f)[0]
        for f in os.listdir(PROFILES_DIR)
        if f.endswith((".yaml", ".yml"))
    )


def _resolve_path(name: str) -> str:
    for ext in (".yaml", ".yml"):
        candidate = os.path.join(PROFILES_DIR, name + ext)
        if os.path.exists(candidate):
            return candidate

    known = available()
    hint = (
        f"Available profiles: {', '.join(known)}"
        if known
        else "No profiles exist yet -- copy profiles/example.yaml to "
        "profiles/<yourname>.yaml and edit it."
    )
    raise ProfileError(f"No profile named '{name}' in {PROFILES_DIR}.\n{hint}")


def _parse_bot(raw: dict[str, Any], where: str) -> BotSpec:
    if not isinstance(raw, dict):
        raise ProfileError(f"{where} must be a mapping, got {type(raw).__name__}.")

    for required in ("ign", "bot"):
        if not raw.get(required):
            raise ProfileError(f"{where} is missing required key '{required}'.")

    settings = raw.get("settings") or {}
    if not isinstance(settings, dict):
        raise ProfileError(f"{where}.settings must be a mapping, or omitted.")

    unknown = set(raw) - {"ign", "bot", "settings"}
    if unknown:
        raise ProfileError(
            f"{where} has unexpected key(s): {', '.join(sorted(unknown))}. "
            "Bot options belong under 'settings:'."
        )

    return BotSpec(ign=str(raw["ign"]), bot=str(raw["bot"]), settings=dict(settings))


def load(name: str) -> Profile:
    """Read and validate `profiles/<name>.yaml`."""
    path = _resolve_path(name)
    with open(path, encoding="utf-8") as fh:
        try:
            raw = yaml.safe_load(fh)
        except yaml.YAMLError as exc:
            raise ProfileError(f"{path} is not valid YAML:\n{exc}") from exc

    if not isinstance(raw, dict):
        raise ProfileError(f"{path} must contain a top-level mapping.")

    unknown = set(raw) - {"ign", "bot", "settings", "mules"}
    if unknown:
        raise ProfileError(
            f"{path} has unexpected top-level key(s): {', '.join(sorted(unknown))}."
        )

    main = _parse_bot(
        {k: v for k, v in raw.items() if k != "mules"}, f"{os.path.basename(path)}"
    )
    mules = [
        _parse_bot(entry, f"{os.path.basename(path)} mules[{i}]")
        for i, entry in enumerate(raw.get("mules") or [])
    ]
    return Profile(name=name, main=main, mules=mules)


def check_models(spec: BotSpec) -> None:
    """
    Fail early and legibly when a profile points at weights nobody downloaded.

    Without this the failure surfaces deep inside model registration, well after
    the game client has been grabbed, as a bare assertion about a path.
    """
    models = spec.settings.get("models_path") or {}
    for label, path in models.items():
        resolved = path if os.path.exists(path) else os.path.join(ROOT, path)
        if not os.path.exists(os.path.join(resolved, "weights", "best.pt")):
            raise ProfileError(
                f"Model '{label}' for {spec.ign} is not on disk: expected "
                f"{os.path.join(path, 'weights', 'best.pt')}\n"
                "Download the published weights with:\n"
                "    python scripts/fetch_models.py"
            )
