import functools
import logging
from collections.abc import Callable
from typing import Protocol

from botting import PARENT_LOG
from botting.core import BotData
from botting.screen import Reading
from maple.decision_makers.pathing import current_physics, read_resolution
from maple.decision_makers.providers.destination import DestinationProvider
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics import (
    MovementHandler,
    compile_movements,
)
from maple.model.mechanics.movement_mechanics_v2 import _MovementComponent
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import FootholdGraphs, Path, Point
from maple.model.world import WorldMap
from maple.screen.position import VirtualPosition

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class NextTargetMixin:
    """
    Legacy: what an unported DecisionMaker used to make and steer the rotation's
    target with. `DestinationProvider` serves it now, as `DESTINATION` (legacy
    name `next_target`), and holds its modes (#441); this only asks for it, and
    steers it for the parked `InventoryManager`. Goes with the last mixin.
    """

    data: BotData

    def _create_rotation_attributes(self) -> None:
        """Ask `BotData` to build `DestinationProvider`, unless it is built already."""
        self.data.build_provider(DestinationProvider)

    def _set_fixed_target(self, target: Point) -> None:
        """
        Move to a fixed target, in virtual px (where the buffs are cast, say).

        Unscoped and unchecked, for unported code only: a ported DecisionMaker
        claims `DESTINATION` with `fixed(target)` instead.
        """
        if _has_destination(self.data):
            # Snapshot first: the hijack is undone by restoring the Provider's
            # exact update function.
            self.data.snapshot_attribute("next_target")
            self.data.reconfigure_attribute(
                "next_target",
                update_function=lambda: target,
            )
            self._reset_flag = True

    def _restore_rotation_target(self) -> None:
        """Undoes a next_target hijack, putting back the Provider's update function."""
        if _has_destination(self.data):
            self.data.restore_attribute("next_target")


def _has_destination(data: BotData) -> bool:
    """Whether the Bot built `DestinationProvider`: whether there is a target."""
    return data.providers is not None and DestinationProvider in data.providers


def planned_movements(data: BotData) -> tuple[_MovementComponent, ...] | None:
    """
    The Movement Plan the rotation planned last, planned again when stale;
    None when no DecisionMaker of the Bot plans one (`MovementsMixin`).

    For a DecisionMaker ported off the mixins that reads the rotation's plan
    (`TelecastMobsHitting`), until a Provider serves it (#442).
    """
    if not data.has_pathing_attributes:
        return None
    return data.movements


def movement_compiler(
    data: BotData,
    physics: VRPhysics,
    *,
    read_at: float | None,
    correlation_id: str | None,
) -> functools.partial:
    """
    The current Movement Plan's compile, its inputs frozen into a picklable
    callable (`MovementsMixin._movement_compiler`, which says why).
    :param data: The Bot's data, whose plan, handle, character and pathing
        statics are frozen.
    :param physics: The character's physics now.
    :param read_at: When the frame the Path was planned from was captured: the
        compile leads the plan by how far the character has walked since. None
        gives no lead.
    :param correlation_id: The decision it belongs to.
    """
    return functools.partial(
        compile_movements,
        movements=data.movements,
        handle=data.handle,
        ign=data.ign,
        speed=physics.walk_speed,
        climb_speed=physics.climb_speed,
        teleport=data.character.skills.get("Teleport"),
        total_duration=data.action_duration,
        always_release=data.always_release_keys,
        walk_acceleration=physics.walk_acceleration,
        walk_deceleration=physics.walk_deceleration,
        read_at=read_at,
        # Baked in here, inside `_decide()`: the compile runs in Main Process,
        # where only this partial knows which decision it belongs to (ADR 0001).
        # The sequence's key records carry it (#538).
        correlation_id=correlation_id,
    )


class MovementsMixin:
    """
    Plans a Path on the map's `FootholdGraph`, from the character's virtual
    position (`current_position`) to the target, and ships its Movement Plan.

    **The target.** `_virtual_target` gives it in virtual px: `next_target`,
    `DESTINATION` by its legacy name, which `DestinationProvider` picks on the
    map's platforms (#398), or whoever claims it serves (`TrialRunner`, whose
    driver owns it, plans through a `MovementPlanner`).

    **An unsure position holds.** When `current_position` is `UNSURE` (the
    minimap placed no character: its marker unplaced, say), no Path is planned
    this cycle: the plan is empty, nothing is sent, and the next cycle plans
    from the next read. A coarse position plans like a fused one, with no walk
    inside its read (`read_resolution`, #516). A position off every platform
    and rope (in the air) holds the same way. The minimap's own failures still
    go to its error handler (`MinimapAttributesMixin._get_position`). On a map
    with no minimap, or none known, no position is read and nothing is
    planned: that is logged once, when the attributes are made.

    **The physics follow the stats.** Each Path is planned on the graph of
    `_physics()`: `VRPhysics` from the game's `Physics.img` (`game_physics`),
    the character's current `speed_multiplier` and `jump_multiplier`, and the
    profile's Calibration constants. When a stat changes, the next Path is
    planned on a graph built for it (`MovementHandler`), and the plan is
    compiled with its speeds.

    **The graph is built off the decision loop** (#430). Its build starts when
    the pathing attributes are made, at the DecisionMaker's setup, with the
    stats known then; a stat change starts the next one when a Path is next
    planned. The build runs in a worker thread (`FootholdGraphs`), shared by
    every DecisionMaker of the Bot (`data.foothold_graphs`, one per teleport
    setting). **While the graph
    of the current stats builds, planning holds**, as for an unsure position:
    no Path is planned on the previous stats' graph, whose jump ranges and
    flights are another arc's, and none on a half-built graph.
    """

    data: BotData
    NO_PATH_FOUND_THRESHOLD: float = 15.0

    def _create_pathing_attributes(
        self,
        duration: float,
        *,
        narrow_platform_threshold: float | None = None,
        edge_departure_threshold: float | None = None,
    ) -> None:
        """
        :param duration: The Action duration cap a Movement Plan is compiled against.
        :param narrow_platform_threshold: Overrides the platform width (virtual px)
            below which a jump or teleport gets its landing direction-stop. `None`
            leaves `MovementHandler`'s default in place, which is what production
            wants; a Trial batch sweeping the precision-movement Knob is the one
            caller that passes anything else.
        :param edge_departure_threshold: Overrides the distance (virtual px) from a
            platform's end within which a jump or teleport gets its pre-departure
            stop. Same shape as `narrow_platform_threshold`.
        """
        self.data.set_static("action_duration", duration)
        self.data.create_or_reconfigure_attribute(
            "movement_handler",
            lambda: self._new_handler(
                narrow_platform_threshold, edge_departure_threshold
            ),
        )
        handler: MovementHandler | None = self.data.movement_handler
        if handler is not None:
            # Built now, off the loop, so the first Path doesn't wait for it.
            handler.graphs.prepare(self._physics())

        self.data.create_or_reconfigure_attribute(
            "path", self._plan_path, threshold=0.1
        )
        self.data.create_or_reconfigure_attribute(
            "movements", self._plan_movements, threshold=0.1
        )
        # No compiled `action` attribute: nothing is compiled in this process any
        # more. A DecisionMaker decides from `movements` and ships the plan, which
        # Main Process compiles at dispatch against the Held-Keys Ledger (ADR 0002).
        self.data.set_static("always_release_keys", False)
        self.data.set_feature("has_pathing_attributes")

    def _new_handler(
        self,
        narrow_platform_threshold: float | None,
        edge_departure_threshold: float | None,
    ) -> MovementHandler | None:
        """
        The map's `MovementHandler`; `None`, logged, on a map with no minimap or
        none known, where no virtual position is read: nothing is planned there.
        """
        world_map: WorldMap | None = getattr(self.data, "world_map", None)
        if world_map is None or world_map.minimap is None:
            logger.warning(
                "%s plans no Path: the bot's map isn't known, or has no minimap.",
                self,
            )
            return None
        teleport = self._teleport_skill()
        return MovementHandler(
            self.data.handle,
            world_map,
            self.data.ign,
            teleport,
            narrow_platform_threshold=narrow_platform_threshold,
            edge_departure_threshold=edge_departure_threshold,
            graphs=self._graphs(world_map, teleport=teleport is not None),
        )

    def _graphs(self, world_map: WorldMap, *, teleport: bool) -> FootholdGraphs:
        """
        The Bot's `FootholdGraphs` for `world_map` and `teleport`, made the first
        time: every handler of the Bot plans on the same graphs, so a graph is
        built once however many DecisionMakers plan, or however often a handler
        is remade (a Trial batch remakes it). One is kept per teleport setting,
        so Trial batches that alternate planning with and without teleport
        build each setting's graph once, not at every switch.
        """
        kept: dict[bool, FootholdGraphs] | None = getattr(
            self.data, "foothold_graphs", None
        )
        if kept is None or any(g.world_map is not world_map for g in kept.values()):
            kept = {}
            self.data.set_static("foothold_graphs", kept)
        graphs = kept.get(teleport)
        if graphs is None:
            graphs = kept[teleport] = FootholdGraphs(world_map, teleport=teleport)
        return graphs

    def _teleport_skill(self) -> MapleSkill | None:
        """
        The teleport skill Paths may cast: the character's, or `None` when it has
        none. A Trial batch planned without it overrides this (`TrialRunner`).
        """
        return self.data.character.skills.get("Teleport")

    def _world_map(self) -> WorldMap:
        world_map: WorldMap | None = getattr(self.data, "world_map", None)
        if world_map is None or world_map.minimap is None:
            raise ValueError(
                "no map to plan on: the bot's map isn't known, or has no minimap"
            )
        return world_map

    def _physics(self) -> VRPhysics:
        """The character's physics, with its current speed and jump stats."""
        return current_physics(self.data)

    def _virtual_target(self) -> Point:
        """The target, in virtual px: `next_target` (see the class docstring)."""
        target = self.data.next_target
        return float(target[0]), float(target[1])

    def _plan_path(self) -> Path | None:
        """The Path from the current position to the target; `None` holds."""
        handler: MovementHandler | None = self.data.movement_handler
        if handler is None:
            return None
        reading: Reading[VirtualPosition] = self.data.current_position
        if reading.value is None:
            logger.debug("No Path: the position is unsure (%s).", reading.detail)
            return None
        physics = self._physics()
        graph = handler.ready_graph(physics)
        if graph is None:
            logger.debug("No Path: the foothold graph of the current stats builds.")
            return None
        position = (float(reading.value.x), float(reading.value.y))
        # The frame the Path starts from: the compile leads the plan by how far
        # the character has walked since (`_movement_compiler`).
        self._path_read_at: float | None = reading.frame_time
        return handler.compute_path(
            position,
            self._virtual_target(),
            physics,
            graph=graph,
            resolution=read_resolution(reading.value, self._world_map()),
        )

    def _plan_movements(self) -> tuple[_MovementComponent, ...]:
        """The Movement Plan of the current Path; empty with no handler."""
        handler: MovementHandler | None = self.data.movement_handler
        if handler is None:
            return ()
        return handler.path_into_movements(self.data.path)

    def _has_movements(self) -> bool:
        """
        Whether the current Movement Plan compiles to anything at all. A plan holding
        nothing but the END_OF_MOVEMENT sentinel produces no Input Sequence - this is
        the live replacement for the old `data.action is not None` check, which could
        only be made by compiling first.
        """
        movements = self.data.movements
        return movements is not None and len(movements) > 1

    def _movement_compiler(self) -> functools.partial:
        """
        Freezes the compile inputs for the current Movement Plan into a picklable
        callable, to be handed to `controller.compile_and_send` inside an
        ActionRequest. Main Process calls it with the Held-Keys Ledger's entry for
        this handle, from inside the focus-lock critical section.

        `MovementHandler` itself cannot travel: its per-instance `lru_cache` wrappers
        are unpicklable. The speeds are the current physics': a jump's flight is
        already in its component, from the graph its Path was planned on.

        **Walks stop where planned** (#503): the walk's acceleration and slide,
        and the capture time of the frame the Path was planned from, let the
        compile time the first and last walks by where the character comes to
        rest, at dispatch (`compile_movements`, `_time_walks`). A host whose
        plan was not planned here (no Path read) gets no lead.
        """
        return movement_compiler(
            self.data,
            self._physics(),
            read_at=getattr(self, "_path_read_at", None),
            correlation_id=getattr(self, "correlation_id", None),
        )


class _Owner(Protocol):
    """Who a `MovementPlanner` plans for: names it, and its decision in flight."""

    correlation_id: str | None


class MovementPlanner(MovementsMixin):
    """
    `MovementsMixin`'s planning, held by a DecisionMaker ported off the mixins
    rather than inherited (`TrialRunner`), until a Provider serves the pathing
    data (#442). It plans to `DESTINATION`, as the mixin does, and names itself
    and its decision after its owner. Goes with the mixin.
    """

    def __init__(
        self,
        owner: _Owner,
        data: BotData,
        *,
        teleport: Callable[[], bool] = lambda: True,
    ) -> None:
        """
        :param owner: The DecisionMaker it plans for.
        :param teleport: Whether Paths may cast the character's teleport skill
            now (a Trial batch planned without it says no).
        """
        self.owner = owner
        self.data = data
        self._teleport = teleport

    def __repr__(self) -> str:
        return repr(self.owner)

    @property
    def correlation_id(self) -> str | None:
        """The owner's decision in flight, which its compile carries."""
        return self.owner.correlation_id

    def create(
        self,
        duration: float,
        *,
        narrow_platform_threshold: float | None = None,
        edge_departure_threshold: float | None = None,
    ) -> None:
        """Make, or remake, the pathing data (`_create_pathing_attributes`)."""
        self._create_pathing_attributes(
            duration,
            narrow_platform_threshold=narrow_platform_threshold,
            edge_departure_threshold=edge_departure_threshold,
        )

    def physics(self) -> VRPhysics:
        """The character's physics now."""
        return self._physics()

    def has_movements(self) -> bool:
        """Whether the current Movement Plan compiles to anything."""
        return self._has_movements()

    def compiler(self) -> functools.partial:
        """The current Movement Plan's compile (`_movement_compiler`)."""
        return self._movement_compiler()

    def _teleport_skill(self) -> MapleSkill | None:
        return super()._teleport_skill() if self._teleport() else None
