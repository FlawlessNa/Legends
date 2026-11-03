import logging
import random
from functools import cached_property, lru_cache

import numpy as np

from botting import PARENT_LOG
from botting.models_abstractions import BaseMap, BaseMob

from .maple_mob import MapleMob
from .minimap_creation.minimap_edits_model import (
    _DEFAULT_NODE_INFO,
    MinimapEdits,
    MinimapEditsManager,
)
from .minimap_creation.minimap_grid import ConnectionTypes, MinimapGrid, MinimapNode
from .physics import MinimapPhysics

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MapleMinimap:
    """
    The map's minimap as data, built entirely from a MinimapEditsManager (JSON
    config): its walkable canvas, features, portals and grid. Physics is
    optional; omitting it disables physics-based grid connections (jumps,
    teleport).

    It reads nothing off the screen. The character's position and where the
    minimap is drawn come from `maple.screen.minimap`.
    """

    JUMP_DOWN_LIMIT: int = 30
    TELEPORT_DOWN_MIN_DIST: int = 3
    _CACHE_MAXSIZE = 256

    def __init__(
        self,
        map_name: str,
        features_manager: MinimapEditsManager,
        physics: MinimapPhysics | None = None,
    ) -> None:
        self.map_name = map_name
        self.physics = physics
        self.features_manager = features_manager
        raw_canvas = self.features_manager.build_canvas()
        self.raw_minimap = self._preprocess_canvas(raw_canvas)
        self.modified_minimap = self.features_manager.apply_grid_edits(
            self.raw_minimap, apply_weights=True
        )
        # Per-instance, bounded caches. An `@lru_cache` on the method keys on `self`,
        # so every minimap ever built stays alive for the process lifetime - the same
        # leak issue #8 removed from the movement pipeline.
        self.generate_grid = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._generate_grid_uncached
        )
        self._get_node_info = lru_cache(maxsize=self._CACHE_MAXSIZE)(
            self._get_node_info_uncached
        )

    @cached_property
    def feature_cycle(self) -> list[MinimapEdits]:
        features = [f for f in self.features_manager.features if f.is_in_rotation]
        indexed = []
        for feature in features:
            for idx in feature.rotation_indexes:
                indexed.append((idx, feature))
        indexed.sort(key=lambda x: x[0])
        return [feature for _, feature in indexed]

    def random_point(self) -> tuple[int, int]:
        y, x = random.choice(np.argwhere(self.modified_minimap))
        # np.argwhere yields np.int64; cast so the annotation is true.
        return int(x), int(y)

    @property
    def party_rebuff_spot(self) -> tuple[int, int] | None:
        """
        The (x, y) gathering coordinate for synchronized rebuffs, from the map's
        JSON config, or None when the map defines none.
        """
        return self.features_manager.party_rebuff_zone

    def get_feature_containing(self, position: tuple[int, int]) -> MinimapEdits | None:
        x, y = position
        return self.features_manager.get_feature_containing(x, y)

    @property
    def map_area_width(self) -> int:
        """The map area's width in minimap pixels, as the map file records it."""
        return self._canvas_size()[0]

    @property
    def map_area_height(self) -> int:
        """The map area's height in minimap pixels, as the map file records it."""
        return self._canvas_size()[1]

    @property
    def map_id(self) -> int | None:
        """The client's id for this map, when its file names it."""
        return self.features_manager.map_id

    def _canvas_size(self) -> tuple[int, int]:
        width = self.features_manager.canvas_width
        height = self.features_manager.canvas_height
        if width is None or height is None:
            raise RuntimeError(
                f"'{self.map_name}' has no canvas_width/canvas_height in its map "
                "file: record it with the map editor."
            )
        return width, height

    def _generate_grid_uncached(
        self,
        allow_teleport: bool,
        speed_multiplier: float,
        jump_multiplier: float,
        include_portals: bool = True,
    ) -> MinimapGrid:
        physics = self._require_physics()
        logger.info(
            "Generating grid for %s, allow_teleport=%r, speed_multiplier=%r, "
            "jump_multiplier=%r, include_portals=%r",
            self.map_name,
            allow_teleport,
            speed_multiplier,
            jump_multiplier,
            include_portals,
        )
        height = physics.get_jump_height(jump_multiplier)
        distance = physics.get_jump_distance(speed_multiplier, jump_multiplier)
        displacement_speed = physics.get_minimap_speed(speed_multiplier)

        grid = MinimapGrid(
            self.modified_minimap, speed=displacement_speed, grid_id=self.map_name
        )
        walkable_nodes = self.modified_minimap.nonzero()
        y_coords, x_coords = walkable_nodes
        for x, y in zip(x_coords, y_coords):
            # `nonzero` yields np.intp; cast so the `node` annotation is true.
            node = grid.node(int(x), int(y))
            info = self.get_node_info(node)
            node.walkable = info.walkable
            node.weight = info.weight
            if not info.walkable:
                self.modified_minimap[y, x] = 0

        self._add_vertical_connections(grid, ConnectionTypes.JUMP, height)
        self._add_vertical_connections(grid, ConnectionTypes.JUMP_DOWN)
        self._add_parabolic_jump_connections(grid, distance, height)
        self._add_fall_connections(grid, distance, height)
        if include_portals:
            self._add_portals(grid)

        if allow_teleport:
            self._add_vertical_connections(grid, ConnectionTypes.TELEPORT_UP)
            self._add_vertical_connections(grid, ConnectionTypes.TELEPORT_DOWN)
            self._add_horizontal_teleport_connections(grid)
        return grid

    @staticmethod
    def _preprocess_canvas(canvas: np.ndarray) -> np.ndarray:
        if len(canvas.shape) == 3 and canvas.shape[-1] == 3:
            return np.where(np.any(canvas > 0, axis=-1), 1, 0).astype(np.uint8)
        else:
            return np.where(canvas > 0, 1, 0).astype(np.uint8)

    def _require_physics(self) -> MinimapPhysics:
        """
        `physics` is optional on a `MapleMinimap` - a map's JSON config may omit
        `scale_x`/`scale_y`, which disables every physics-based connection. Only grid
        generation needs it, so the requirement is stated here rather than widened
        into the constructor.
        """
        if self.physics is None:
            raise RuntimeError(
                f"Cannot generate grid for '{self.map_name}': physics parameters "
                f"(scale_x, scale_y) are not set in the map's JSON config."
            )
        return self.physics

    def get_node_info(self, node: MinimapNode) -> MinimapEdits:
        x, y = node.x, node.y
        assert node.grid_id == self.map_name, (
            f"Cannot retrieve info for a node from another map: "
            f"{node.grid_id=} != {self.map_name=}"
        )
        return self._get_node_info(x, y)

    def _get_node_info_uncached(self, x: int, y: int) -> MinimapEdits:
        return self.features_manager.get_feature_containing(x, y) or _DEFAULT_NODE_INFO

    def _add_vertical_connections(
        self,
        grid: MinimapGrid,
        conn_type: ConnectionTypes,
        jump_height: float | None = None,
    ) -> None:
        physics = self._require_physics()

        def _get_range(start: MinimapNode) -> range:
            if conn_type == ConnectionTypes.JUMP:
                assert jump_height is not None, "JUMP connections need a jump height"
                return range(start.y - round(jump_height), start.y)
            elif conn_type == ConnectionTypes.JUMP_DOWN:
                return range(
                    start.y + 1,
                    min(start.y + self.JUMP_DOWN_LIMIT + 1, grid.height - 1),
                )
            elif conn_type == ConnectionTypes.TELEPORT_UP:
                return range(start.y - round(physics.teleport_v_up_dist) - 1, start.y)
            elif conn_type == ConnectionTypes.TELEPORT_DOWN:
                return range(
                    min(
                        start.y + round(physics.teleport_v_down_dist) + 1,
                        grid.height - 1,
                    ),
                    start.y + self.TELEPORT_DOWN_MIN_DIST,
                    -1,
                )
            raise ValueError(f"{conn_type!r} is not a vertical connection type")

        for row in grid.nodes:
            for node in row:
                if not node.walkable or self.get_node_info(node).is_ladder:
                    continue

                for other_node in (grid.node(node.x, k) for k in _get_range(node)):
                    x2, y2 = other_node.x, other_node.y
                    other_feature = self.get_node_info(other_node)
                    cond1 = other_node.walkable
                    cond2 = other_feature.is_platform
                    cond3 = not other_feature.is_a_blocked_endpoint(x2, y2)
                    if cond1 and cond2 and cond3:
                        node.connect(other_node, conn_type)
                        break

    def _add_parabolic_jump_connections(
        self, grid: MinimapGrid, jump_dist: float, jump_height: float
    ) -> None:
        physics = self._require_physics()
        for row in grid.nodes:
            for node in row:
                if not node.walkable:
                    continue

                node_info = self.get_node_info(node)

                if node_info.is_platform:
                    if node_info.is_a_blocked_endpoint(node.x, node.y):
                        continue

                    left_jump = physics.get_jump_trajectory(
                        node.x,
                        node.y,
                        "left",
                        jump_dist,
                        jump_height,
                        grid.width,
                        grid.height,
                    )
                    right_jump = physics.get_jump_trajectory(
                        node.x,
                        node.y,
                        "right",
                        jump_dist,
                        jump_height,
                        grid.width,
                        grid.height,
                    )
                    self._parse_trajectory(grid, node, right_jump)
                    self._parse_trajectory(grid, node, left_jump)

                elif node_info.is_ladder:
                    left_jump = physics.get_jump_trajectory(
                        node.x,
                        node.y,
                        "left",
                        jump_dist,
                        jump_height,
                        grid.width,
                        grid.height,
                        True,
                    )
                    right_jump = physics.get_jump_trajectory(
                        node.x,
                        node.y,
                        "right",
                        jump_dist,
                        jump_height,
                        grid.width,
                        grid.height,
                        True,
                    )
                    self._parse_trajectory(grid, node, right_jump)
                    self._parse_trajectory(grid, node, left_jump)

    def _parse_trajectory(
        self,
        grid: MinimapGrid,
        node: MinimapNode,
        trajectory: list[tuple[int, int]],
        fall: bool = False,
    ) -> None:
        highest_y = min(trajectory, key=lambda i: i[1])[1]
        apogee = list(filter(lambda pos: pos[1] == highest_y, trajectory))
        apogee_idx = trajectory.index(apogee[0])
        mid = len(apogee) // 2
        if len(apogee) % 2 == 0:
            nodes_for_rope = apogee[mid - 1 : mid + 1]
        else:
            nodes_for_rope = apogee[mid : mid + 1]
        idx = trajectory.index(nodes_for_rope[-1])
        nodes_for_rope = trajectory[idx : idx + 3]

        furthest = max(trajectory, key=lambda i: (i[0], i[1]))
        if furthest == trajectory[0]:
            connection = (
                ConnectionTypes.FALL_LEFT if fall else ConnectionTypes.JUMP_LEFT
            )
        elif furthest == trajectory[-1]:
            connection = (
                ConnectionTypes.FALL_RIGHT if fall else ConnectionTypes.JUMP_RIGHT
            )
        else:
            # A trajectory whose extreme point is neither end has no left/right sense.
            # This used to fall through to an `UnboundLocalError` on the first
            # `node.connect` below; the failure is unchanged, only named.
            raise ValueError(
                f"Cannot orient a trajectory whose furthest point {furthest} is "
                f"neither its start {trajectory[0]} nor its end {trajectory[-1]}."
            )

        neighbors = grid.adjacent_nodes(node, diagonal=True)
        node_info = self.get_node_info(node)

        for x, y in trajectory:
            other_node = grid.node(x, y)
            if other_node == node or not other_node.walkable or other_node in neighbors:
                continue
            other_info = self.get_node_info(other_node)
            if other_info == node_info:
                break
            elif other_info.is_platform and trajectory.index((x, y)) >= apogee_idx:
                node.connect(other_node, connection)
                break
            elif (
                other_info.is_ladder and (other_node.x, other_node.y) in nodes_for_rope
            ):
                node.connect(other_node, connection)

    def _add_fall_connections(
        self, grid: MinimapGrid, jump_dist: float, jump_height: float
    ) -> None:
        physics = self._require_physics()
        for row in grid.nodes:
            for node in row:
                if not node.walkable:
                    continue

                node_info = self.get_node_info(node)
                direction = []

                if node_info.is_platform and grid.is_left_edge(node):
                    direction.append("left")
                elif node_info.is_platform and grid.is_right_edge(node):
                    direction.append("right")

                for d in direction:
                    traj = physics.get_jump_trajectory(
                        node.x,
                        node.y,
                        d,
                        jump_dist,
                        jump_height,
                        grid.width,
                        grid.height,
                        fall=True,
                    )
                    self._parse_trajectory(grid, node, traj, fall=True)

    def _add_portals(self, grid: MinimapGrid) -> None:
        for portal in self.features_manager.portals:
            src = grid.node(*portal.source)
            tgt = grid.node(*portal.target)
            src.connect(tgt, ConnectionTypes.IN_MAP_PORTAL)
            if portal.bidirectional:
                tgt.connect(src, ConnectionTypes.IN_MAP_PORTAL)

    def _add_horizontal_teleport_connections(self, grid: MinimapGrid) -> None:
        physics = self._require_physics()

        def _parse_range(
            x: int, y_start: int, y_rng: int, conn_type: ConnectionTypes
        ) -> None:
            for y in range(y_start, y_start - y_rng - 1, -1):
                other_node = grid.node(x, y)
                if other_node.walkable and self.get_node_info(other_node).is_platform:
                    node.connect(other_node, conn_type)
                    return
            for y in range(y_start + 1, y_start + y_rng + 1):
                other_node = grid.node(x, y)
                if other_node.walkable and self.get_node_info(other_node).is_platform:
                    node.connect(other_node, conn_type)
                    return

        vertical_rng = round(physics.teleport_v_up_dist / 2)
        for row in grid.nodes:
            for node in row:
                node_info = self.get_node_info(node)
                if (
                    not node.walkable
                    or node_info.is_ladder
                    or node_info.is_a_blocked_endpoint(node.x, node.y)
                ):
                    continue

                left_x = max(0, round(node.x - physics.teleport_h_dist))
                right_x = min(round(node.x + physics.teleport_h_dist), grid.width - 1)

                _parse_range(
                    left_x, node.y, vertical_rng, ConnectionTypes.TELEPORT_LEFT
                )
                _parse_range(
                    right_x, node.y, vertical_rng, ConnectionTypes.TELEPORT_RIGHT
                )


class MapleMap(BaseMap):
    """
    Holds the map and its associated data. The minimap is built entirely from a
    JSON config (MinimapEditsManager). No game-file parser is required.

    MapleMob instantiation is deferred until mob IDs are supplied externally
    (e.g. from the ML training pipeline).
    TODO: inject mob IDs from ML pipeline rather than game files.
    """

    def __init__(
        self,
        map_name: str,
        open_minimap_editor: bool = False,
        *,
        include_character_position: bool = True,
        scale: int = 5,
        ign: str | None = None,
    ) -> None:
        self.map_name = map_name
        self.edits = MinimapEditsManager.from_json(map_name) or MinimapEditsManager()
        physics = self._build_physics(self.edits)
        self.minimap = MapleMinimap(map_name, self.edits, physics)

        if open_minimap_editor:
            from .minimap_creation.map_editor import MinimapEditor

            editor = MinimapEditor(
                self.minimap,
                self.edits,
                include_character_position=include_character_position,
                scale=scale,
                # `MinimapEditor` declares `ign: str = None`, an implicit optional it
                # cannot express; None is its own default and is handled.
                ign=ign,  # pyright: ignore[reportArgumentType]
            )
            self.edits = editor.edits
            physics = self._build_physics(self.edits)
            self.minimap = MapleMinimap(map_name, self.edits, physics)

        self.mobs: tuple[BaseMob, ...] = tuple(
            MapleMob(name) for name in self.edits.mobs
        )

    @staticmethod
    def _build_physics(edits: MinimapEditsManager) -> MinimapPhysics | None:
        if edits.scale_x is not None and edits.scale_y is not None:
            return MinimapPhysics(edits.scale_x, edits.scale_y)
        return None
