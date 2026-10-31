"""
Launch a bot from a profile.

Usage
-----
    python -m maple.launchers.run <profile>
    python -m maple.launchers.run --list

`<profile>` names a file under `profiles/` -- `profiles/farmacy.yaml` is
launched as `farmacy`. Copy `profiles/example.yaml` to get started; see
`docs/FIRST_BOT.md` for the whole walkthrough.

Everything that used to be edited into a launcher script (character name, map,
skills, model) now lives in the profile, so nobody has to touch tracked source
to run their own setup.
"""

from __future__ import annotations

import argparse
import asyncio
import multiprocessing.managers
import sys

import maple.parsers
from botting.core import Bot
from botting.core.session_manager import SessionManager
from maple import bots

from .profile import BotSpec, Profile, ProfileError, available, check_models, load


def _bot_registry() -> dict[str, type]:
    """
    Map the profile's `bot:` value to a class exported by `maple.bots`.

    Both the class name and its "Bot"-less shorthand are accepted, so
    `bot: TrainingBot` and `bot: training` resolve to the same class. Built by
    inspection rather than hand-maintained, so uncommenting an export in
    `maple/bots/__init__.py` is enough to make it available to profiles.
    """
    registry: dict[str, type] = {}
    for name in dir(bots):
        if name.startswith("_"):
            continue
        obj = getattr(bots, name)
        if isinstance(obj, type):
            registry[name.lower()] = obj
            registry.setdefault(name.lower().removesuffix("bot"), obj)
    return registry


def _resolve(spec: BotSpec) -> type:
    registry = _bot_registry()
    cls = registry.get(spec.bot.lower())
    if cls is None:
        exported = sorted({c.__name__ for c in registry.values()})
        raise ProfileError(
            f"Unknown bot '{spec.bot}' for {spec.ign}.\n"
            f"Currently available: {', '.join(exported)}\n"
            "If the bot you want is missing, check that it is exported from "
            "maple/bots/__init__.py."
        )
    return cls


def _build(spec: BotSpec, metadata: multiprocessing.managers.DictProxy) -> Bot:
    cls = _resolve(spec)
    check_models(spec)
    return cls(spec.ign, metadata, **spec.settings)


async def _run(profile: Profile) -> None:
    """
    Launch the profile's bot in a single Engine group.
    """
    with SessionManager(maple.parsers.MapleParser) as session:
        await session.launch([_build(profile.main, session.metadata)])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m maple.launchers.run",
        description="Launch a bot from a profile under profiles/.",
    )
    parser.add_argument(
        "profile", nargs="?", help="Profile name, without the .yaml extension."
    )
    parser.add_argument(
        "--list", action="store_true", help="List the profiles on disk and exit."
    )
    parser.add_argument(
        "--debug", action="store_true", help="Run the asyncio loop in debug mode."
    )
    args = parser.parse_args(argv)

    if args.list:
        names = available()
        listing = "\n".join(f"  {n}" for n in names) if names else "  (no profiles yet)"
        sys.stdout.write(listing + "\n")
        return 0

    if not args.profile:
        parser.error("a profile name is required (or pass --list)")

    try:
        profile = load(args.profile)
    except ProfileError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2

    try:
        asyncio.run(_run(profile), debug=args.debug)
    except ProfileError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
