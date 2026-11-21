"""
The rotation's pathing: the Path from the character's virtual position to
`DESTINATION` on the map's foothold graph, its Movement Plan, and what that plan
is compiled with at dispatch.

`PathingProvider` serves the `MovementHandler`, the Path, the Movement Plan,
the Action duration cap and the release flag (#442). It is built once per Bot,
when a DecisionMaker reads one of its keys (`Rotation`, `TrialRunner`), and
configured from the profile: `movements_duration` is the cap,
`disable_teleport` plans and compiles with no teleport skill.

**The target.** A Path is planned to `DESTINATION`, which `DestinationProvider`
picks on the map's platforms, or whoever claims it serves (`TrialRunner`, whose
driver owns it).

**An unsure position holds.** When `POSITION` is `UNSURE` (the minimap placed no
character: its marker unplaced, say), no Path is planned this cycle: the plan is
empty, nothing is sent, and the next cycle plans from the next read. A coarse
position plans like a fused one, with no walk inside its read
(`read_resolution`, #516). A position off every platform and rope (in the air)
holds the same way. The minimap's own failures still go to its error handler
(`MinimapProvider`). On a map with no minimap, or none known, no position is
read and nothing is planned: that is logged once, at setup.

**The physics follow the stats.** Each Path is planned on the graph of
`physics()`: `VRPhysics` from the game's `Physics.img` (`GAME_PHYSICS`), the
character's current speed and jump (the ability menu's when the Bot read them,
the profile's otherwise), and the profile's Calibration constants. When a stat
changes, the next Path is planned on a graph built for it (`MovementHandler`),
and the plan is compiled with its speeds.

**The graph is built off the decision loop** (#430). Its build starts at setup,
with the stats known then; a stat change starts the next one when a Path is next
planned. The build runs in a worker thread (`FootholdGraphs`), one per teleport
setting, kept by the Provider. **While the graph of the current stats builds,
planning holds**, as for an unsure position: no Path is planned on the previous
stats' graph, whose jump ranges and flights are another arc's, and none on a
half-built graph.
"""

import functools
import logging
from collections.abc import Callable, Sequence
from typing import Any, NamedTuple

from botting import PARENT_LOG
from botting.core import HANDLE, BotData, Key, Provider
from botting.screen import Reading
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics import MovementHandler, compile_movements
from maple.model.mechanics.movement_mechanics_v2 import _MovementComponent
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import FootholdGraphs, Path
from maple.model.world import Platform, WorldMap
from maple.screen.position import PositionSource, VirtualPosition

from .destination import DESTINATION
from .map import GAME_PHYSICS, WORLD_MAP
from .menus import JUMP_MULTIPLIER, SPEED_MULTIPLIER
from .minimap import POSITION
from .profile import CALIBRATION, PROFILE_JUMP_MULTIPLIER, PROFILE_SPEED_MULTIPLIER
from .skills import SKILLS

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

#: The Movement Plan's type: its components, END_OF_MOVEMENT last.
MovementPlan = tuple[_MovementComponent, ...]


class PathingProvider(Provider):
    """
    Serves the `MovementHandler`, the Path to `DESTINATION` and its Movement
    Plan, the Action duration cap and the release flag.

    Configured from the profile: `movements_duration` is the cap a plan is
    compiled against, and `disable_teleport` plans and compiles with no
    teleport skill. The teleport skill is `SKILLS`' `Teleport`, which nothing
    here changes, and only when its cast time is known: a Teleport with none
    is planned as no teleport, logged at setup. `setup()` makes the handler, starts
    building its graph, and plans the first Path. A Trial batch changes the cap,
    the precision Knobs and whether Paths may teleport with `configure`.
    """

    needs = (
        HANDLE,
        SKILLS,
        WORLD_MAP,
        GAME_PHYSICS,
        POSITION,
        DESTINATION,
        PROFILE_SPEED_MULTIPLIER,
        PROFILE_JUMP_MULTIPLIER,
        CALIBRATION,
    )

    #: Seconds a Path and a Movement Plan are served before a read plans again.
    REFRESH = 0.1

    def __init__(
        self,
        *args: Any,  # noqa: ANN401 - Provider's own
        movements_duration: float = 1.0,
        disable_teleport: bool = False,
        **settings: object,
    ) -> None:
        """
        :param movements_duration: The Action duration cap a Movement Plan is
            compiled against, in seconds.
        :param disable_teleport: Plan and compile with no teleport skill.
        """
        super().__init__(*args, **settings)
        self.disable_teleport = disable_teleport
        self._duration = movements_duration
        #: The precision Knobs: `None` leaves `MovementHandler`'s defaults.
        self._narrow_platform_threshold: float | None = None
        self._edge_departure_threshold: float | None = None
        #: Whether Paths may cast the character's teleport skill (`configure`).
        self._teleport = True
        #: The graphs every handler of this Bot plans on, one per teleport setting.
        self._graphs: dict[bool, FootholdGraphs] = {}
        #: When the frame the current Path was planned from was captured.
        self._path_read_at: float | None = None

    def setup(self) -> None:
        self._warn_of_a_teleport_with_no_cast_time()
        self.register(ACTION_DURATION, lambda: self._duration)
        self.register(MOVEMENT_HANDLER, self._new_handler)
        handler = self.read(MOVEMENT_HANDLER)
        if handler is not None:
            # Built now, off the loop, so the first Path doesn't wait for it.
            handler.graphs.prepare(self.physics())
        self.register(PATH, self._plan_path, threshold=self.REFRESH)
        self.register(MOVEMENTS, self._plan_movements, threshold=self.REFRESH)
        # No compiled Action: nothing is compiled in the Engine. A DecisionMaker
        # decides from `MOVEMENTS` and ships the plan, which Main Process
        # compiles at dispatch against the Held-Keys Ledger (ADR 0002).
        self.register(ALWAYS_RELEASE_KEYS, lambda: False)

    # --- what others ask of it ---------------------------------------------------

    def configure(
        self,
        *,
        duration: float,
        narrow_platform_threshold: float | None = None,
        edge_departure_threshold: float | None = None,
        teleport: bool = True,
    ) -> None:
        """
        Change what Paths are planned and compiled with, and make the handler
        again: what a Trial batch's Knobs sweep (`TrialRunner`). The new handler
        plans on the graphs already built for its teleport setting, and starts
        building the graph of the current stats for it if none is, as setup
        does.
        :param duration: The Action duration cap.
        :param narrow_platform_threshold: The platform width (virtual px) below
            which a jump or teleport gets its landing direction-stop; `None`
            leaves `MovementHandler`'s default.
        :param edge_departure_threshold: The distance (virtual px) from a
            platform's end within which a jump or teleport gets its
            pre-departure stop; `None` leaves the default.
        :param teleport: Whether Paths may cast the character's teleport skill.
        """
        self._duration = duration
        self._narrow_platform_threshold = narrow_platform_threshold
        self._edge_departure_threshold = edge_departure_threshold
        self._teleport = teleport
        self.refresh(ACTION_DURATION)
        handler = self.refresh(MOVEMENT_HANDLER)
        if handler is not None:
            handler.graphs.prepare(self.physics())

    def physics(self) -> VRPhysics:
        """
        The character's physics, with its current speed and jump stats.

        The speed and jump are the ability menu's, `SPEED_MULTIPLIER` and
        `JUMP_MULTIPLIER`, when the Bot built `AbilityMenuProvider` and so read
        them (the last read: nothing here refreshes them, nor causes the
        Provider to be built); otherwise the profile's
        (`PROFILE_SPEED_MULTIPLIER`, `PROFILE_JUMP_MULTIPLIER`). The Calibration
        constants are the profile's too (`CALIBRATION`).
        :raises ValueError: The game's physics aren't known (no map).
        """
        values = self.read(GAME_PHYSICS)
        if values is None:
            raise ValueError("no game physics: the bot's map isn't known")
        speed = self.data.peek(SPEED_MULTIPLIER)
        jump = self.data.peek(JUMP_MULTIPLIER)
        return VRPhysics.from_game_files(
            values,
            speed_multiplier=(
                self.read(PROFILE_SPEED_MULTIPLIER) if speed is None else speed
            ),
            jump_multiplier=(
                self.read(PROFILE_JUMP_MULTIPLIER) if jump is None else jump
            ),
            calibration=self.read(CALIBRATION),
        )

    def compiler(
        self, correlation_id: str | None, *, lead: bool = True
    ) -> functools.partial:
        """
        The current Movement Plan's compile, its inputs frozen into a picklable
        callable, for `controller.compile_and_send` inside an ActionRequest.
        Main Process calls it with the Held-Keys Ledger's entry for the handle,
        from inside the focus-lock critical section.

        `MovementHandler` itself cannot travel: its per-instance `lru_cache`
        wrappers are unpicklable. The speeds are the current physics': a jump's
        flight is already in its component, from the graph its Path was planned
        on.

        **Walks stop where planned** (#503): the walk's acceleration and slide,
        and the capture time of the frame the Path was planned from, let the
        compile time the first and last walks by where the character comes to
        rest, at dispatch (`compile_movements`, `_time_walks`).
        :param correlation_id: The decision it belongs to. Baked in here: the
            compile runs in Main Process, where only this partial knows which
            decision it belongs to (ADR 0001). The sequence's key records carry
            it (#538).
        :param lead: Lead the plan by how far the character has walked since
            the frame its Path was planned from. A DecisionMaker that compiles a
            plan another planned passes False: no lead.
        """
        physics = self.physics()
        return functools.partial(
            compile_movements,
            movements=self.read(MOVEMENTS),
            handle=self.read(HANDLE),
            ign=self.data.ign,
            speed=physics.walk_speed,
            climb_speed=physics.climb_speed,
            teleport=self._profile_teleport(),
            total_duration=self.read(ACTION_DURATION),
            always_release=self.read(ALWAYS_RELEASE_KEYS),
            walk_acceleration=physics.walk_acceleration,
            walk_deceleration=physics.walk_deceleration,
            read_at=self._path_read_at if lead else None,
            correlation_id=correlation_id,
        )

    def reachable_platforms(self) -> tuple[Platform, ...] | None:
        """
        The platforms a Path reaches from the character's last position read,
        on the graph of its current physics. `None` while that isn't known: no
        `MovementHandler` on this map, the graph of the current physics still
        building, no position read or an unsure one, or a position on no
        surface (in the air).

        Reads no position: it is the last one read. The graph is never waited
        for: while it builds off the loop (#430), asking starts its build if
        nothing had, and answers `None`.
        """
        handler = self.read(MOVEMENT_HANDLER)
        last = self.data.peek(POSITION)
        if handler is None or last is None or last.value is None:
            return None
        graph = handler.ready_graph(self.physics())
        if graph is None:
            return None
        try:
            surfaces = graph.reachable((last.value.x, last.value.y))
        except ValueError:
            return None
        platforms = tuple(s for s in surfaces if isinstance(s, Platform))
        return platforms or None

    # --- the update functions ----------------------------------------------------

    def _new_handler(self) -> MovementHandler | None:
        """
        The map's `MovementHandler`; `None`, logged, on a map with no minimap or
        none known, where no virtual position is read: nothing is planned there.
        """
        world_map = self.read(WORLD_MAP)
        if world_map is None or world_map.minimap is None:
            logger.warning(
                "%s plans no Path: the bot's map isn't known, or has no minimap.",
                self,
            )
            return None
        teleport = self._teleport_skill()
        return MovementHandler(
            self.read(HANDLE),
            world_map,
            self.data.ign,
            teleport,
            narrow_platform_threshold=self._narrow_platform_threshold,
            edge_departure_threshold=self._edge_departure_threshold,
            graphs=self._graphs_for(world_map, teleport=teleport is not None),
        )

    def _graphs_for(self, world_map: WorldMap, *, teleport: bool) -> FootholdGraphs:
        """
        The `FootholdGraphs` for `world_map` and `teleport`, made the first
        time: every handler plans on the same graphs, so a graph is built once
        however often a handler is made again (a Trial batch makes it again).
        One is kept per teleport setting, so Trial batches that alternate
        planning with and without teleport build each setting's graph once, not
        at every switch.
        """
        if any(g.world_map is not world_map for g in self._graphs.values()):
            self._graphs = {}
        graphs = self._graphs.get(teleport)
        if graphs is None:
            graphs = self._graphs[teleport] = FootholdGraphs(
                world_map, teleport=teleport
            )
        return graphs

    def _teleport_skill(self) -> MapleSkill | None:
        """
        The teleport skill Paths may cast: the character's, or `None` when it
        has none, or a Trial batch plans without it (`configure`).
        """
        if not self._teleport:
            return None
        return self._profile_teleport()

    def _profile_teleport(self) -> MapleSkill | None:
        """
        `SKILLS`' `Teleport`; `None` when the character has none, the profile's
        `disable_teleport` takes it away, or its cast time isn't known.

        No Teleport of the client's has an action of its own: its cast time is
        its effect's duration (#646), and some have no effect. A Movement Plan
        that cast one with no cast time couldn't be compiled, so Paths walk.
        """
        if self.disable_teleport:
            return None
        teleport = self.read(SKILLS).get("Teleport")
        if teleport is None or teleport.cast_time is None:
            return None
        return teleport

    def _warn_of_a_teleport_with_no_cast_time(self) -> None:
        """Say once, at setup, that the character's Teleport isn't planned."""
        teleport = self.read(SKILLS).get("Teleport")
        if self.disable_teleport or teleport is None or teleport.cast_time is not None:
            return
        logger.warning(
            "%s plans no teleport: %s (%d) has no cast time in the game data "
            "(no action, and no effect to time it), so Paths walk.",
            self,
            teleport.name,
            teleport.id,
        )

    def _plan_path(self) -> Path | None:
        """The Path from the current position to `DESTINATION`; `None` holds."""
        handler = self.read(MOVEMENT_HANDLER)
        if handler is None:
            return None
        world_map = self.read(WORLD_MAP)
        assert world_map is not None, "a handler is made only on a known map"
        planned = plan_path(
            handler,
            self.read(POSITION),
            world_map,
            physics=self.physics,
            target=lambda: self.read(DESTINATION),
        )
        if planned is None:
            return None
        # The frame the Path starts from: the compile leads the plan by how far
        # the character has walked since (`compiler`).
        self._path_read_at = planned.read_at
        return planned.path

    def _plan_movements(self) -> MovementPlan:
        """The Movement Plan of the current Path; empty with no handler."""
        handler = self.read(MOVEMENT_HANDLER)
        if handler is None:
            return ()
        return handler.path_into_movements(self.read(PATH))


#: The Action duration cap a Movement Plan is compiled against, in seconds.
ACTION_DURATION: Key[float] = Key("action_duration", PathingProvider)
#: The map's `MovementHandler`, or None on a map with no minimap: nothing is
#: planned there. Made again only when asked to (`configure`).
MOVEMENT_HANDLER: Key[MovementHandler | None] = Key("movement_handler", PathingProvider)
#: The Path from the character to `DESTINATION`, in virtual px; None holds.
PATH: Key[Path | None] = Key("path", PathingProvider)
#: The Movement Plan of `PATH`: its components, END_OF_MOVEMENT last; empty with
#: no handler.
MOVEMENTS: Key[MovementPlan] = Key("movements", PathingProvider)
#: Whether every key still held at the end of a Movement Plan is released.
ALWAYS_RELEASE_KEYS: Key[bool] = Key("always_release_keys", PathingProvider)


class PlannedPath(NamedTuple):
    """A Path planned from a position read (`plan_path`)."""

    #: The Path, or None when none joins the position to the target.
    path: Path | None
    #: When the frame the Path starts from was captured: a compile leads the
    #: plan by how far the character has walked since.
    read_at: float


def plan_path(
    handler: MovementHandler,
    reading: Reading[VirtualPosition],
    world_map: WorldMap,
    *,
    physics: Callable[[], VRPhysics],
    target: Callable[[], Sequence[float]],
) -> PlannedPath | None:
    """
    The Path from `reading` to the target, on `handler`'s graph of the current
    physics: how `PathingProvider` plans, and the movement playground with it.

    `None` holds, planning nothing: the position is unsure, or the graph of the
    current physics still builds (#430). A coarse position plans with no walk
    inside its read (`read_resolution`, #516).
    :param world_map: The map `handler` plans on.
    :param physics: The physics to plan with, asked once the position is sure.
    :param target: Where the Path ends, in virtual px, asked once a graph is
        ready: reading it can refresh it (`DESTINATION`), which a cycle that
        holds must not.
    """
    if reading.value is None:
        logger.debug("No Path: the position is unsure (%s).", reading.detail)
        return None
    planned_with = physics()
    graph = handler.ready_graph(planned_with)
    if graph is None:
        logger.debug("No Path: the foothold graph of the current stats builds.")
        return None
    end = target()
    path = handler.compute_path(
        (float(reading.value.x), float(reading.value.y)),
        (float(end[0]), float(end[1])),
        planned_with,
        graph=graph,
        resolution=read_resolution(reading.value, world_map),
    )
    return PlannedPath(path, reading.frame_time)


def actionable(plan: MovementPlan | None) -> bool:
    """
    Whether a Movement Plan compiles to anything at all. A plan holding nothing
    but the END_OF_MOVEMENT sentinel produces no Input Sequence: this is what
    tells a plan worth sending, without compiling it.
    """
    return plan is not None and len(plan) > 1


def read_resolution(position: VirtualPosition, world_map: WorldMap) -> float:
    """
    How far off a read's x may be, in virtual px: half a canvas px for a
    coarse read (the middle of the canvas pixel the feet are in), 0 for a
    fused one. A walk no longer than that is no move (#516,
    `MovementHandler.compute_path`).
    """
    if position.source is not PositionSource.COARSE or world_map.minimap is None:
        return 0.0
    return world_map.minimap.scale / 2


def reachable_platforms(data: BotData) -> tuple[Platform, ...] | None:
    """
    `PathingProvider.reachable_platforms`, once the Bot's is set up; `None`
    before, or with no pathing: nothing is known then of which platforms a
    Path reaches. For `DestinationProvider`, which `PathingProvider` needs, so
    it cannot need this Provider's keys back, and is set up first.
    """
    providers = data.providers
    if providers is None or not data.is_provided(MOVEMENT_HANDLER):
        return None
    return providers.get(PathingProvider).reachable_platforms()


def pathing(data: BotData) -> PathingProvider:
    """
    The Bot's `PathingProvider`: for a DecisionMaker that asks it for the
    physics or a compile, beside reading its keys.
    :raises LookupError: The Bot built none: nothing reads its keys.
    """
    providers = data.providers
    assert providers is not None, "the Bot attaches its Providers to its data"
    return providers.get(PathingProvider)
