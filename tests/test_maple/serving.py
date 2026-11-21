"""
A Bot's data with its Bot-level Providers, built as `Bot.child_init` and
`MapleBot.child_init` build them, from stand-ins: no client, no sprites.

The client shows whatever `frames` returns, one call per capture. The screen
readers are the test's own, by `ScreenReadersProvider`'s keywords (`chat=`,
`buffs=`...). Assembly then builds whatever else a DecisionMaker reads, as it
does for a Bot: `assemble(served, SomeDecisionMaker)`.
"""

import queue
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from botting.core import (
    BotData,
    DecisionMaker,
    Key,
    Providers,
    RepliesProvider,
    WindowProvider,
)
from botting.core.data_keys import resolve_providers
from botting.screen import Reading, capture
from maple.decision_makers.providers import (
    AREA_PRESENCE,
    AREA_STRETCHES,
    ATTACKS,
    DESTINATION,
    FRAME,
    HUNTING_AREA,
    POSITION,
    SKILLS,
    AreaPresence,
    Attack,
    AttacksProvider,
    CharacterProvider,
    ClientProvider,
    DestinationProvider,
    HuntingAreaProvider,
    MapProvider,
    MinimapProvider,
    MobsProvider,
    PathingProvider,
    ProfileProvider,
    ScreenReadersProvider,
    SkillsProvider,
)
from maple.model.characters.maple_skills import MapleSkill
from maple.model.characters.reach import Armed, Reach
from maple.model.navigation import Point
from maple.model.world import HuntingArea, Stretch, WorldMap
from maple.screen.position import VirtualPosition


class Client:
    """The client's capture: each grab shows what `frames` returns."""

    def __init__(self, frames: Callable[[], object]) -> None:
        self.frames = frames
        self.grabs = 0

    def grab(self, handle: int) -> object:
        self.grabs += 1
        return self.frames()


class Proxies:
    """Main Process's proxies, made here: a Condition is a thread's, a Queue a
    thread-safe queue's."""

    def instance(self, key: str, primitive_type: str) -> object:
        if primitive_type == "Queue":
            return queue.Queue()
        return getattr(threading, primitive_type)()


@dataclass
class Served:
    """What `serve` built."""

    data: BotData
    providers: Providers
    client: Client
    #: The replies switch, as `Bot.replies` switches it.
    replies: RepliesProvider
    pipe: Any = field(default=None)


def serve(
    monkeypatch: pytest.MonkeyPatch,
    ign: str = "Bot",
    *,
    pipe: Any = None,  # noqa: ANN401 - whatever records what is sent
    proxies: Any = None,  # noqa: ANN401 - a ProxyFactory, or a stand-in
    data: BotData | None = None,
    frames: Callable[[], object] = lambda: None,
    handle: int = 1,
    chat_keys: Mapping[str, str] | None = None,
    character: object = None,
    buff_names: tuple[str, ...] = (),
    skills: Mapping[str, object] | None = None,
    **readers: object,
) -> Served:
    """
    `ign`'s data, with the window, the replies switch, the screen readers, the
    character and its skills when they are given, and the client's frame and
    chat keys.

    :param frames: What the client shows, one call per capture.
    :param character: What `CHARACTER` serves; none is served without one,
        or without `buff_names`, which its Provider serves too.
    :param skills: What `SKILLS` serves; none is served without them.
    :param readers: The screen readers, by `ScreenReadersProvider`'s keywords.
    """
    client = Client(frames)
    monkeypatch.setattr(capture, "_source", client)
    data = data or BotData(ign)
    providers = Providers(data, pipe, proxies or Proxies(), {})  # pyright: ignore[reportArgumentType] - a stand-in
    providers.add(WindowProvider, handle=handle)
    replies = providers.add(RepliesProvider)
    assert isinstance(replies, RepliesProvider)
    providers.add(ScreenReadersProvider, sprites=None, **readers)
    if character is not None or buff_names:
        providers.add(
            CharacterProvider,
            character_class=lambda *_: character,
            buff_names=buff_names,
        )
    if skills is not None:
        # Built as `MapleBot.child_init` builds it, from `skills` rather than
        # the keybindings and the catalogue.
        monkeypatch.setattr(SkillsProvider, "_skills", lambda _: dict(skills))
        providers.add(SkillsProvider, job="Beginner")
    providers.add(ClientProvider, chat_keys=dict(chat_keys or {}))
    return Served(data, providers, client, replies, pipe)


def serve_skills(data: BotData, skills: Mapping[str, object]) -> None:
    """`SKILLS`, registered as `SkillsProvider` registers it, from `skills`: no
    keybindings, no catalogue. For a Provider built on its own; a DecisionMaker
    assembled on a Bot needs `serve(skills=...)`, which builds the Provider."""
    data.provide(
        SKILLS, object.__new__(SkillsProvider), lambda: skills, initial_value=skills
    )


#: What a fixture attack reaches: 100 px each side of the feet, 100 above and 50
#: below.
WIDE_REACH = Reach(-100, -100, 100, 50)


def attack(min_mobs: int, reach: Reach = WIDE_REACH, name: str = "Fixture") -> Attack:
    """An attack of the profile's `attacks`, with the box `reach` and no client."""
    skill = MapleSkill(name, id=0, level=1, max_level=1)
    return Attack(Armed(skill, reach), min_mobs)


def destination(
    world_map: WorldMap,
    at: Callable[[], Reading[VirtualPosition]],
    *,
    data: BotData | None = None,
    frame: Callable[[], object] = lambda: None,
    position_fusion: object = None,
    game_physics: Mapping[str, float] | None = None,
    handle: int = 0,
    area: HuntingArea | None = None,
    stretches: tuple[Stretch, ...] | None = None,
    presence: AreaPresence | None = None,
    attacks: tuple[Attack, ...] | None = None,
    **settings: object,
) -> DestinationProvider:
    """
    `DestinationProvider`, built and set up as assembly builds it, with the
    profile `settings`, on a Bot whose map is `world_map` and whose position is
    `at`'s, read once, as a Session has.

    The window, the map and its mobs (none) are served by their Bot-level
    Providers; `POSITION` and `FRAME` are registered as `MinimapProvider` and
    `ClientProvider` register them, from `at` and `frame`, with no client.
    The Hunting Area's keys and `ATTACKS` are registered as their Providers
    register them, from `area`, `stretches`, `presence` and `attacks`: None,
    as with a rotation other than `hunting_area`, unless given; `override`
    changes them.
    """
    data = data or BotData("T")
    providers = data.providers or Providers(data, None, Proxies(), settings)  # pyright: ignore[reportArgumentType] - nothing is sent
    providers.settings.update(settings)
    providers.add(WindowProvider, handle=handle)
    providers.add(
        MapProvider,
        map_id=0,
        world_map=world_map,
        game_physics=game_physics,
        position_fusion=position_fusion,
    )
    providers.add(MobsProvider)
    data.provide(FRAME, object.__new__(ClientProvider), frame)
    data.provide(POSITION, object.__new__(MinimapProvider), at, initial_value=at())
    data.update_attribute(POSITION.name)
    area_provider = object.__new__(HuntingAreaProvider)
    data.provide(HUNTING_AREA, area_provider, lambda: area)
    data.provide(AREA_STRETCHES, area_provider, lambda: stretches)
    data.provide(AREA_PRESENCE, area_provider, lambda: presence)
    data.provide(ATTACKS, object.__new__(AttacksProvider), lambda: attacks)
    providers.build([DestinationProvider])
    return providers.get(DestinationProvider)


def pathing(
    world_map: WorldMap,
    at: Callable[[], Reading[VirtualPosition]],
    target: Callable[[], Point] = lambda: (0.0, 0.0),
    *,
    data: BotData | None = None,
    skills: Mapping[str, object] | None = None,
    game_physics: Mapping[str, float] | None = None,
    handle: int = 0,
    position_threshold: float | None = None,
    **settings: object,
) -> PathingProvider:
    """
    `PathingProvider`, built and set up as assembly builds it, with the
    profile `settings`, on a Bot whose map is `world_map`, whose skills are
    `skills` (none when not given), whose position is `at`'s and whose destination is `target`'s,
    with the profile's stats (`ProfileProvider`): 1, unless `settings` give
    them, and no Calibration constant.

    On a `data` that `destination` served, its window, map, position and
    `DestinationProvider` are the ones used, and `target` is not.
    :param position_threshold: `POSITION`'s refresh threshold; None reads it
        only when asked to.
    """
    data = data or BotData("T")
    providers = data.providers or Providers(data, None, Proxies(), settings)  # pyright: ignore[reportArgumentType] - nothing is sent
    providers.settings.update(settings)
    if WindowProvider not in providers:
        providers.add(WindowProvider, handle=handle)
    if MapProvider not in providers:
        providers.add(
            MapProvider, map_id=0, world_map=world_map, game_physics=game_physics
        )
    if not data.is_provided(SKILLS):
        serve_skills(data, skills or {})
    if not data.is_provided(POSITION):
        data.provide(
            POSITION,
            object.__new__(MinimapProvider),
            at,
            threshold=position_threshold,
            initial_value=at(),
        )
    if not data.is_provided(DESTINATION):
        data.provide(DESTINATION, object.__new__(DestinationProvider), target)
    if ProfileProvider not in providers:
        providers.add(ProfileProvider)
    providers.build([PathingProvider])
    return providers.get(PathingProvider)


#: `override`'s "leave the value as it is".
_KEEP = object()


def override(
    data: BotData,
    key: Key[Any],
    update_function: Callable[[], object] | None = None,
    *,
    threshold: float | None = None,
    value: object = _KEEP,
) -> None:
    """
    Stand in for what `key`'s Provider reads off the client: its update function,
    its refresh threshold, or both, from now on; or the value it holds now,
    claimed or not. Whatever is not given is kept, the history included.

    For tests only: production code steers a key with a Claim.
    """
    managed = data._managed[key.name]  # pyright: ignore[reportPrivateUsage] - the stand-in's seam
    if update_function is not None:
        managed.update_function = update_function
    if threshold is not None:
        managed.threshold = threshold
    if value is not _KEEP:
        managed.set(value)


def assemble(served: Served, *classes: type[DecisionMaker]) -> None:
    """Build the Providers `classes` read, as assembly does."""
    served.providers.build(resolve_providers(classes))
