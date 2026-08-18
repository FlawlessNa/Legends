import logging
import numpy as np
import random
from functools import lru_cache, cached_property
from botting import PARENT_LOG
from botting.models_abstractions import BaseMap, BaseMob
from .game_file_extraction.map_physics import MinimapPhysics
from .maple_mob import MapleMob
from .minimap_creation.minimap_edits_model import (
    MinimapEditsManager,
    MinimapEdits,
    _DEFAULT_NODE_INFO,
)
from .minimap_creation.minimap_grid import MinimapNode, MinimapGrid, ConnectionTypes
from ..interface import Minimap

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MapleMinimap(Minimap):
    """
    Minimap built entirely from a MinimapEditsManager (JSON config).
    No game-file parser required. Physics is optional; omitting it disables
    physics-based grid connections (jumps, teleport).
    """

    JUMP_DOWN_LIMIT: int = 30
    TELEPORT_DOWN_MIN_DIST: int = 3

    def __init__(
        self,
        map_name: str,
        features_manager: MinimapEditsManager,
        physics: MinimapPhysics | None = None,
    ):
        self.map_name = map_name
        self.physics = physics
        self.features_manager = features_manager
        raw_canvas = self.features_manager.build_canvas()
        self.raw_minimap = self._preprocess_canvas(raw_canvas)
        self.modified_minimap = self.features_manager.apply_grid_edits(
            self.raw_minimap, apply_weights=True
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
        return x, y

    def get_feature_containing(self, position: tuple[int, int]) -> MinimapEdits | None:
        x, y = position
        return self.features_manager.get_feature_containing(x, y)

    @property
    def map_area_width(self) -> int:
        if self.features_manager.canvas_width is None:
            return NotImplemented
        return self.features_manager.canvas_width

    @property
    def map_area_height(self) -> int:
        if self.features_manager.canvas_height is None:
            return NotImplemented
        return self.features_manager.canvas_height

    @lru_cache
    def generate_grid(
        self,
        allow_teleport: bool,
        speed_multiplier: float,
        jump_multiplier: float,
        include_portals: bool = True,
    ) -> MinimapGrid:
        if self.physics is None:
            raise RuntimeError(
                f"Cannot generate grid for '{self.map_name}': physics parameters "
                f"(scale_x, scale_y) are not set in the map's JSON config."
            )
        logger.info(
            f"Generating grid for {self.map_name}, {allow_teleport=}, "
            f"{speed_multiplier=}, {jump_multiplier=}, {include_portals=}"
        )
        height = self.physics.get_jump_height(jump_multiplier)
        distance = self.physics.get_jump_distance(speed_multiplier, jump_multiplier)
        displacement_speed = self.physics.get_minimap_speed(speed_multiplier)

        grid = MinimapGrid(
            self.modified_minimap, speed=displacement_speed, grid_id=self.map_name
        )
        walkable_nodes = self.modified_minimap.nonzero()
        y_coords, x_coords = walkable_nodes
        for x, y in zip(x_coords, y_coords):
            node = grid.node(x, y)
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

    _preprocess_img = _preprocess_canvas

    def get_node_info(self, node: MinimapNode) -> MinimapEdits:
        x, y = node.x, node.y
        assert node.grid_id == self.map_name, (
            f"Cannot retrieve info for a node from another map: "
            f"{node.grid_id=} != {self.map_name=}"
        )
        return self._get_node_info(x, y)

    @lru_cache
    def _get_node_info(self, x: int, y: int) -> MinimapEdits:
        return self.features_manager.get_feature_containing(x, y) or _DEFAULT_NODE_INFO

    def _add_vertical_connections(
        self, grid: MinimapGrid, conn_type: ConnectionTypes, jump_height: float = None
    ) -> None:

        def _get_range(start: MinimapNode) -> range:
            if conn_type == ConnectionTypes.JUMP:
                return range(start.y - round(jump_height), start.y)
            elif conn_type == ConnectionTypes.JUMP_DOWN:
                return range(
                    start.y + 1, min(start.y + self.JUMP_DOWN_LIMIT + 1, grid.height - 1)
                )
            elif conn_type == ConnectionTypes.TELEPORT_UP:
                return range(
                    start.y - round(self.physics.teleport_v_up_dist) - 1, start.y
                )
            elif conn_type == ConnectionTypes.TELEPORT_DOWN:
                return range(
                    min(
                        start.y + round(self.physics.teleport_v_down_dist) + 1,
                        grid.height - 1
                    ),
                    start.y + self.TELEPORT_DOWN_MIN_DIST,
                    -1
                )

        assert conn_type in (
            ConnectionTypes.JUMP,
            ConnectionTypes.JUMP_DOWN,
            ConnectionTypes.TELEPORT_UP,
            ConnectionTypes.TELEPORT_DOWN,
        )

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
        for row in grid.nodes:
            for node in row:
                if not node.walkable:
                    continue

                node_info = self.get_node_info(node)

                if node_info.is_platform:
                    if node_info.is_a_blocked_endpoint(node.x, node.y):
                        continue

                    left_jump = self.physics.get_jump_trajectory(
                        node.x, node.y, "left", jump_dist, jump_height,
                        grid.width, grid.height,
                    )
                    right_jump = self.physics.get_jump_trajectory(
                        node.x, node.y, "right", jump_dist, jump_height,
                        grid.width, grid.height,
                    )
                    self._parse_trajectory(grid, node, right_jump)
                    self._parse_trajectory(grid, node, left_jump)

                elif node_info.is_ladder:
                    left_jump = self.physics.get_jump_trajectory(
                        node.x, node.y, "left", jump_dist, jump_height,
                        grid.width, grid.height, True,
                    )
                    right_jump = self.physics.get_jump_trajectory(
                        node.x, node.y, "right", jump_dist, jump_height,
                        grid.width, grid.height, True,
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
            nodes_for_rope = apogee[mid - 1: mid + 1]
        else:
            nodes_for_rope = apogee[mid: mid + 1]
        idx = trajectory.index(nodes_for_rope[-1])
        nodes_for_rope = trajectory[idx: idx + 3]

        if max(trajectory, key=lambda i: (i[0], i[1])) == trajectory[0]:
            connection = ConnectionTypes.FALL_LEFT if fall else ConnectionTypes.JUMP_LEFT
        elif max(trajectory, key=lambda i: (i[0], i[1])) == trajectory[-1]:
            connection = ConnectionTypes.FALL_RIGHT if fall else ConnectionTypes.JUMP_RIGHT

        neighbors = grid.neighbors(node, MinimapGrid.ALL_DIAGONAL_NEIGHBORS, False)
        node_info = self.get_node_info(node)

        for x, y in trajectory:
            other_node = grid.node(x, y)
            if other_node == node or not other_node.walkable or other_node in neighbors:
                continue
            other_info = self.get_node_info(other_node)
            if other_info == node_info:
                break
            elif other_info.is_platform and trajectory.index((x, y)) >= apogee_idx:
                node.connect(other_node, connection)  # noqa
                break
            elif (
                other_info.is_ladder and (other_node.x, other_node.y) in nodes_for_rope
            ):
                node.connect(other_node, connection)  # noqa

    def _add_fall_connections(
        self, grid: MinimapGrid, jump_dist: float, jump_height: float
    ) -> None:
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
                    traj = self.physics.get_jump_trajectory(
                        node.x, node.y, d, jump_dist, jump_height,
                        grid.width, grid.height, fall=True,
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

        vertical_rng = round(self.physics.teleport_v_up_dist / 2)
        for row in grid.nodes:
            for node in row:
                node_info = self.get_node_info(node)
                if (
                    not node.walkable
                    or node_info.is_ladder
                    or node_info.is_a_blocked_endpoint(node.x, node.y)
                ):
                    continue

                left_x = max(0, round(node.x - self.physics.teleport_h_dist))
                right_x = min(
                    round(node.x + self.physics.teleport_h_dist), grid.width - 1
                )

                _parse_range(left_x, node.y, vertical_rng, ConnectionTypes.TELEPORT_LEFT)
                _parse_range(right_x, node.y, vertical_rng, ConnectionTypes.TELEPORT_RIGHT)


class MapleMap(BaseMap):
    """
    Holds the map and its associated data. The minimap is built entirely from a
    JSON config (MinimapEditsManager). No game-file parser is required.

    MapleMob instantiation is deferred until mob IDs are supplied externally
    (e.g. from the ML training pipeline).
    TODO: inject mob IDs from ML pipeline rather than game files.
    """

    def __init__(
        self, map_name: str, open_minimap_editor: bool = False, **kwargs
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
                include_character_position=kwargs.get("include_character_position", True),
                scale=kwargs.get("scale", 5),
                ign=kwargs.get("ign", None),
            )
            self.edits = editor.edits
            physics = self._build_physics(self.edits)
            self.minimap = MapleMinimap(map_name, self.edits, physics)

        self.mobs: tuple[BaseMob, ...] = tuple(MapleMob(name) for name in self.edits.mobs)

    @staticmethod
    def _build_physics(edits: MinimapEditsManager) -> MinimapPhysics | None:
        if edits.scale_x is not None and edits.scale_y is not None:
            return MinimapPhysics(edits.scale_x, edits.scale_y)
        return None
