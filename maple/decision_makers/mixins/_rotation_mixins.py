import functools
import logging
import math
import statistics
import time
from collections.abc import Callable, Sequence

import numpy as np

from botting import PARENT_LOG
from botting.core import BotData
from botting.screen import Frame, Reading
from maple.model.characters.maple_skills import MapleSkill
from maple.model.mechanics import (
    MovementHandler,
    compile_movements,
)
from maple.model.mechanics.movement_mechanics_v2 import _MovementComponent
from maple.model.mechanics.physics import VRPhysics
from maple.model.navigation import Path, Point
from maple.model.world import Platform, WorldMap
from maple.screen.position import PositionFusion, VirtualPosition, marker_of_feet
from maple.telemetry_events import MOVEMENT_TARGET_REACHED, target_reached_payload

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class NextTargetMixin:
    """
    The rotation's target, in virtual px, on the bot's `WorldMap` (#398).

    **The no-cycle path, on platforms.** A map from `game_data` has no feature
    cycle, so the rotation heads for random points on the map's platforms
    (`WorldMap.random_point`, platforms weighted by their width), and the
    feature a target is on is the platform under it (`next_feature`,
    `WorldMap.platform_at`). Custom rotation patterns are a later epic.

    **Only platforms a Path reaches.** The draw is restricted to the platforms
    the foothold graph reaches from the character's position, when the graph
    and a position are known: some maps have platforms nothing reaches (on
    Damp Forest, 7 of its 11, 37 % of their width, from its widest platform), and a
    target there is one no Path joins, which only movement recovery would
    ever drop. A target drawn before then is checked, and drawn again, once
    they are known.
    """

    data: BotData
    # Supplied by MobsHittingMixin, which smart rotation asserts is co-inherited.
    get_mobs_positions_in_img: Callable[..., list[Sequence[int]]]
    mobs_in_virtual_px: Callable[..., list[Point]]
    #: Arrival for the basic rotation, in virtual px: 10 minimap px, as it was
    #: judged in minimap px before #398 (16 virtual px each, `mag` 4).
    BASE_ROTATION_THRESHOLD = 160.0
    #: Arrival for the "gravitate towards mobs" rotation: 4 minimap px.
    SMART_ROTATION_THRESHOLD = 64.0
    #: How far smart rotation steps towards the mobs at most: 10 minimap px.
    SMART_ROTATION_STEP = 160.0
    TIME_ON_TARGET = 0.75  # Used for "smart rotation" mechanism
    MIN_MOBS_THRESHOLD = 2

    def _create_rotation_attributes(
        self,
        *,
        smart_rotation: bool = False,
        mob_count_threshold: int | None = None,
    ) -> None:
        """
        :raises ValueError: The bot's map isn't known: there is nothing to
            pick a target on.
        """
        if smart_rotation is True:
            self.data.set_feature("has_smart_rotation")
            assert mob_count_threshold is not None, (
                "Mob count threshold must be provided for smart rotation."
            )
            self.data.set_static("mob_threshold", mob_count_threshold)

        world_map = _world_map_of(self.data)
        update = (
            self._smart_rotation_target
            if self.data.has_smart_rotation
            else self._update_next_random_target
        )
        self.data.create_or_reconfigure_attribute(
            "next_target", update, initial_value=self._random_target()
        )
        self.data.create_or_reconfigure_attribute(
            "next_feature", lambda: world_map.platform_at(self.data.next_target)
        )
        self.data.set_feature("has_rotation_attributes")

    # --- targets on platforms ------------------------------------------------

    def _random_target(self) -> Point:
        """
        A random point on the platforms a Path reaches from the character, or
        on every platform before the graph and a position are known.
        """
        world_map = _world_map_of(self.data)
        among = _reachable_platforms(self.data)
        self._target_checked = among is not None
        return world_map.random_point(among)

    def _checked_target(self, target: Point) -> Point:
        """
        `target`, or a fresh draw when it was drawn before reachability was
        known, and the platform it is on turns out to be one no Path reaches
        from the character.
        """
        if getattr(self, "_target_checked", True):
            return target
        among = _reachable_platforms(self.data)
        if among is None:
            return target
        self._target_checked = True
        if _world_map_of(self.data).platform_at(target) in among:
            return target
        logger.info("%s: target %s is on no reachable platform.", self, target)
        redrawn = _world_map_of(self.data).random_point(among)
        self.data.next_feature = _world_map_of(self.data).platform_at(redrawn)
        return redrawn

    def _emit_target_reached(self, position: Point, target: Point) -> None:
        """
        Record that a rotation mode judged the character to have arrived. Every
        place that judges arrival calls this, so the count means one thing.

        `EnsureMobStillSpawn` installs `_update_next_random_target` as its own
        target update while it is active, so its records are attributed to it: a
        count of these against `movement.plan_started` (Rotation only) will run
        higher while it is.

        Takes the values the caller just judged arrival with, rather than reading
        them off `BotData`: a read can refresh a thresholded attribute, and
        telemetry must not do work inside the thing it observes. Both are
        virtual px; the canvas fields are where the minimap draws the marker
        for each (`marker_of_feet`).
        """
        # Not every host of this mixin is a DecisionMaker with `emit`.
        emit = getattr(self, "emit", None)
        world_map: WorldMap | None = getattr(self.data, "world_map", None)
        if emit is None or world_map is None or world_map.minimap is None:
            # No minimap, no position read: nothing is judged to arrive there.
            return
        transform = world_map.minimap
        emit(
            MOVEMENT_TARGET_REACHED,
            target_reached_payload(
                marker_of_feet(transform, position),
                marker_of_feet(transform, target),
                virtual_position=position,
                virtual_target=target,
            ),
        )

    def _update_next_random_target(self) -> Point:
        """
        The current target until the character is within
        `BASE_ROTATION_THRESHOLD` of it, then a new random one. An unsure
        position holds the target: arrival can't be judged from it.
        """
        target = self._checked_target(self.data.next_target)
        reading = read_position(self.data)
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.BASE_ROTATION_THRESHOLD:
            return target
        self._emit_target_reached(position, target)
        next_target = self._random_target()
        self.data.next_feature = _world_map_of(self.data).platform_at(next_target)
        return next_target

    def _abandon_current_target(self) -> Point:
        """
        Drop the target the rotation is heading for and pick a different one.

        Movement recovery's **Abandon** rung (`CONTEXT.md` -> Reaction Ladder).
        The update functions return the *current* target until the character is
        within threshold of it, which is exactly what keeps a Stuck loop stuck:
        re-deciding cannot change where it is going. So the new target is written
        straight onto the attribute: a fresh random point on a reachable
        platform.

        The draw may of course land back on the same platform. That is not worth
        guarding: the ladder is already at Abandon, so the next symptom escalates.
        :return: The new target.
        """
        self.data.next_target = self._random_target()
        self.data.update_attribute("next_feature")
        return self.data.next_target

    def _set_fixed_target(self, target: Point) -> None:
        """
        Move to a fixed target, in virtual px (where the buffs are cast, say).
        """
        if self.data.has_rotation_attributes:
            # Overwrite how the next_target attribute is set until the rebuff is done.
            # Snapshot first: the hijack is undone by restoring the rotation owner's
            # exact update function. Re-deriving it with _create_rotation_attributes
            # from here would rebind it to *this* DecisionMaker instead.
            self.data.snapshot_attribute("next_target")
            self.data.reconfigure_attribute(
                "next_target",
                update_function=lambda: target,
            )
            self._reset_flag = True

    def _restore_rotation_target(self) -> None:
        """
        Undoes a next_target hijack, putting back the update function installed by
        whichever DecisionMaker owns the rotation.
        """
        if self.data.has_rotation_attributes:
            self.data.restore_attribute("next_target")

    def _smart_rotation_target(self) -> Point:
        """
        Determines the next target to move towards in a "smart way".
        Uses current on-screen location to get a wide view on the current platform.
        If there are mobs, target the "average" position of those in the direction
        where there are most, on the target's platform. Otherwise, a random point on
        that platform (the no-cycle path's "next feature").
        :return:
        """
        assert hasattr(self.data, "mob_threshold"), (
            "_mob_threshold attribute must be set."
        )
        assert hasattr(self, "get_mobs_positions_in_img"), (
            f"MobsHittingMixin must be inherited by {self} for smart rotation"
        )
        if not hasattr(self, "_first_time_on_target"):
            self._first_time_on_target = True
        if not hasattr(self, "_last_target_reached_at"):
            self._last_target_reached_at = time.perf_counter()

        target = self._checked_target(self.data.next_target)
        reading = read_position(self.data)
        if reading.value is None:
            return target
        position = (reading.value.x, reading.value.y)
        if math.dist(position, target) > self.SMART_ROTATION_THRESHOLD:
            self._first_time_on_target = True
            return target

        # If we're on target, check if we've been on target for > time_limit seconds.
        if self._first_time_on_target:
            self._emit_target_reached(position, target)
            self._first_time_on_target = False
            self._last_target_reached_at = time.perf_counter()
            return target
        elif time.perf_counter() - self._last_target_reached_at < self.TIME_ON_TARGET:
            return target

        # Reach this code once you've been on target for > time_limit seconds.
        self._first_time_on_target = True
        # Check for mobs in the vicinity
        self.data.update_attribute("current_frame")
        on_screen_pos = self.data.get_last_known_value("current_on_screen_position")
        if on_screen_pos is not None:
            x1, y1, x2, y2 = on_screen_pos
            frame = self.data.current_frame
            shape = frame.pixels.shape
            mask = np.zeros(shape, np.uint8)
            mask[
                max(0, y1 - 100) : min(shape[0], y2 + 100),
                max(0, x1 - 500) : min(shape[1], x2 + 500),
            ] = 255
            mobs_locations = self.get_mobs_positions_in_img(
                frame.pixels, self.data.current_mobs, mask=mask
            )
            if len(mobs_locations) >= max(
                self.data.mob_threshold, self.MIN_MOBS_THRESHOLD
            ):
                stepped = self._step_towards_mobs(mobs_locations, frame, target)
                if stepped is not None:
                    return stepped

        self.data.update_attribute("next_feature")
        platform: Platform | None = self.data.next_feature
        if platform is None:
            return self._random_target()
        return _world_map_of(self.data).random_point((platform,))

    def _step_towards_mobs(
        self, mobs: list[Sequence[int]], frame: Frame, target: Point
    ) -> Point | None:
        """
        A point on the target's platform, towards the side most of `mobs` are on:
        their mean distance from the character, at most `SMART_ROTATION_STEP`.
        The mobs are placed in virtual px through the camera of the frame they
        were found on; `None` when that frame's camera or position isn't read,
        or the target is on no platform.
        """
        # Read on this frame, so its camera is the one that places the mobs.
        self.data.update_attribute("current_position")
        reading: Reading[VirtualPosition] = self.data.current_position
        fusion: PositionFusion | None = getattr(self.data, "position_fusion", None)
        camera = None if fusion is None else fusion.camera
        platform = _world_map_of(self.data).platform_at(target)
        if camera is None or reading.value is None or platform is None:
            return None
        here = reading.value.x
        xs = [x for x, _ in self.mobs_in_virtual_px(mobs, frame.client_size, camera)]
        left = [here - x for x in xs if x < here]
        right = [x - here for x in xs if x >= here]
        if len(left) > len(right):
            x = max(
                here - min(statistics.mean(left), self.SMART_ROTATION_STEP),
                platform.left,
            )
        else:
            x = min(
                here + min(statistics.mean(right), self.SMART_ROTATION_STEP),
                platform.right,
            )
        y = platform.y_at(x)
        return None if y is None else (x, y)


def read_position(data: BotData) -> Reading[VirtualPosition]:
    """
    `current_position`, read when it is stale; `UNSURE`, without a read, on a
    map no position is read on (the map not known, or with no minimap), where a
    read could only fail into the minimap's error handler.
    """
    world_map: WorldMap | None = getattr(data, "world_map", None)
    if world_map is None or world_map.minimap is None:
        return Reading.unsure(0.0, "no position is read on this map")
    return data.current_position


def _world_map_of(data: BotData) -> WorldMap:
    """
    The bot's map.

    :raises ValueError: It isn't known (the profile names no map).
    """
    world_map: WorldMap | None = getattr(data, "world_map", None)
    if world_map is None:
        raise ValueError(
            "no map to rotate on: the bot's map isn't known (name it with the "
            "profile's `map` setting)"
        )
    return world_map


def current_physics(data: BotData) -> VRPhysics:
    """The character's physics, with its current speed and jump stats."""
    values = getattr(data, "game_physics", None)
    if values is None:
        raise ValueError("no game physics: the bot's map isn't known")
    return VRPhysics.from_game_files(
        values,
        speed_multiplier=data.speed_multiplier,
        jump_multiplier=data.jump_multiplier,
        calibration=getattr(data, "calibration", None),
    )


def _reachable_platforms(data: BotData) -> tuple[Platform, ...] | None:
    """
    The platforms a Path reaches from the character's last position read, on
    the graph of its current physics. `None` while that isn't known: no
    `MovementHandler` yet (or none on this map), no position read or an unsure
    one, or a position on no surface (in the air).

    Reads no position: it is the last one read. The graph is the handler's,
    so asking before the first Path builds the graph that Path would build.
    """
    try:
        handler: MovementHandler | None = data.movement_handler
    except AttributeError:
        return None
    last = _last_position(data)
    if handler is None or last is None:
        return None
    try:
        surfaces = handler.graph(current_physics(data)).reachable((last.x, last.y))
    except ValueError:
        return None
    platforms = tuple(s for s in surfaces if isinstance(s, Platform))
    return platforms or None


def _last_position(data: BotData) -> VirtualPosition | None:
    """
    The last virtual position read, without reading one: `None` before the
    first read, or when the bot reads none.
    """
    try:
        last = data.get_last_known_value("current_position", update=False)
    except AttributeError:
        return None
    return None if last is None else last.value


class MovementsMixin:
    """
    Plans a Path on the map's `FootholdGraph`, from the character's virtual
    position (`current_position`) to the target, and ships its Movement Plan.

    **The target.** `_virtual_target` gives it in virtual px: `next_target`,
    which the rotation picks on the map's platforms (`NextTargetMixin`, #398).
    A DecisionMaker whose target is not `next_target` (`TrialRunner`, whose
    driver owns it) overrides it.

    **An unsure position holds.** When `current_position` is `UNSURE` (the
    reads disagree, or two characters stand where the minimap puts ours), no
    Path is planned this cycle: the plan is empty, nothing is sent, and the next
    cycle plans from the next read. A position off every platform and rope (in
    the air) holds the same way. The minimap's own failures still go to its
    error handler (`MinimapAttributesMixin._get_position`). On a map with no
    minimap, or none known, no position is read and nothing is planned: that is
    logged once, when the attributes are made.

    **The physics follow the stats.** Each Path is planned on the graph of
    `_physics()`: `VRPhysics` from the game's `Physics.img` (`game_physics`),
    the character's current `speed_multiplier` and `jump_multiplier`, and the
    profile's Calibration constants. When a stat changes, the next Path is
    planned on a graph built for it (`MovementHandler`), and the plan is
    compiled with its speeds.
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
        return MovementHandler(
            self.data.handle,
            world_map,
            self.data.ign,
            self._teleport_skill(),
            narrow_platform_threshold=narrow_platform_threshold,
            edge_departure_threshold=edge_departure_threshold,
        )

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
        position = (float(reading.value.x), float(reading.value.y))
        return handler.compute_path(position, self._virtual_target(), self._physics())

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
        """
        physics = self._physics()
        return functools.partial(
            compile_movements,
            movements=self.data.movements,
            handle=self.data.handle,
            ign=self.data.ign,
            speed=physics.walk_speed,
            climb_speed=physics.climb_speed,
            teleport=self.data.character.skills.get("Teleport"),
            total_duration=self.data.action_duration,
            always_release=self.data.always_release_keys,
        )
