import logging
import numpy as np
from functools import lru_cache
from botting import PARENT_LOG
from .game_file_extraction.map_parser import MapParser
from .game_file_extraction.map_physics import MinimapPhysics
from .map_creation.minimap_edits_controller import MinimapEditor
from .map_creation.minimap_edits_model import MinimapEditsManager, MinimapEdits
from .map_creation.minimap_grid import MinimapNode, MinimapGrid, ConnectionTypes
from ..interface import Minimap

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")


class MapleMinimap(Minimap):
    """
    Draws the raw minimap from game files.
    If a minimap subclass exists for the current minimap, it loads in the specified
    modifications and modifies the raw minimap based on those.
    """

    JUMP_DOWN_LIMIT: int = 30  # TODO - Make this a parameter or fine-tune (probably in physics?)
    TELEPORT_DOWN_MIN_DIST: int = 3  # TODO - Make this a parameter or fine-tune

    def __init__(
        self,
        parser: MapParser,
        raw_canvas: np.ndarray,
        features_manager: MinimapEditsManager,
        physics: MinimapPhysics,
    ):
        self.map_name = parser.map_name
        self.parser = parser
        self.raw_minimap = self._preprocess_canvas(raw_canvas)
        self.features_manager = features_manager
        self.modified_minimap = self.features_manager.apply_grid_edits(
            self.raw_minimap, apply_weights=True
        )
        self.physics = physics

    def generate_grid(
        self,
        allow_teleport: bool,
        speed_multiplier: float,
        jump_multiplier: float,
        include_portals: bool = True,
    ) -> MinimapGrid:
        logger.info(
            f"Generating grid for {self.map_name}, {allow_teleport=}, "
            f"{speed_multiplier=}, {jump_multiplier=}, {include_portals=}"
        )
        height = self.physics.get_jump_height(jump_multiplier)
        distance = self.physics.get_jump_distance(speed_multiplier, jump_multiplier)

        # Create the grid and set walkable nodes with weights
        # TODO - This needs to be corrected for custom edits with offsets
        grid = MinimapGrid(self.modified_minimap, grid_id=self.map_name)
        walkable_nodes = self.modified_minimap.nonzero()
        y_coords, x_coords = walkable_nodes
        for x, y in zip(x_coords, y_coords):
            node = grid.node(x, y)
            info = self.get_node_info(node)
            node.walkable = info.walkable
            node.weight = info.weight

        self._add_vertical_connections(grid, ConnectionTypes.JUMP_UP, height)
        self._add_vertical_connections(grid, ConnectionTypes.JUMP_DOWN)
        self._add_parabolic_jump_connections(grid, distance, height)
        self._add_fall_connections(grid)
        if include_portals:
            self._add_portals(grid)

        if allow_teleport:
            self._add_vertical_connections(grid, ConnectionTypes.TELEPORT_UP)
            self._add_vertical_connections(grid, ConnectionTypes.TELEPORT_DOWN)
            self._add_horizontal_teleport_connections(grid, ...)
        return grid

    @staticmethod
    def _preprocess_canvas(canvas: np.ndarray) -> np.ndarray:
        """
        Converts the canvas into a binary (unweighted) image.
        """
        if len(canvas.shape) == 3 and canvas.shape[-1] == 3:
            return np.where(np.any(canvas > 0, axis=-1), 1, 0).astype(np.uint8)
        else:
            return np.where(canvas > 0, 1, 0).astype(np.uint8)

    _preprocess_img = _preprocess_canvas

    def get_node_info(self, node: MinimapNode) -> MinimapEdits:
        """
        Returns custom feature for the given node, if any.
        Otherwise, returns the auto-generated feature.
        """
        x, y = node.x, node.y
        return self._get_node_info(x, y)

    @lru_cache
    def _get_node_info(self, x: int, y: int) -> MinimapEdits:
        return self.features_manager.get_features_containing(
            x, y
        ) or self.parser.parse_node(x, y)

    def _add_vertical_connections(
        self, grid: MinimapGrid, conn_type: int, jump_height: float = None
    ) -> None:

        def _get_range(start: MinimapNode) -> range:
            if conn_type == ConnectionTypes.JUMP_UP:
                return range(start.y - round(jump_height), start.y)
            elif conn_type == ConnectionTypes.JUMP_DOWN:
                return range(
                    start.y + 1, min(start.y + self.JUMP_DOWN_LIMIT + 1, grid.height)
                )
            elif conn_type == ConnectionTypes.TELEPORT_UP:
                return range(start.y - self.physics.teleport_v_up_dist - 1, start.y)
            elif conn_type == ConnectionTypes.TELEPORT_DOWN:
                return range(
                    start.y + self.TELEPORT_DOWN_MIN_DIST,
                    min(start.y + self.physics.teleport_v_down_dist + 1, grid.height),
                )

        assert conn_type in (
            ConnectionTypes.JUMP_UP,
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
        """
        Adds connections for parabolic jumps (e.g jumps in a direction).
        """
        for row in grid.nodes:
            for node in row:
                if not node.walkable:
                    continue

                node_info = self.get_node_info(node)

                if node_info.is_platform:
                    if node_info.is_a_blocked_endpoint(node.x, node.y):
                        continue

                    left_jump = self.physics.get_jump_trajectory(
                        node.x, node.y, 'left', jump_dist, jump_height, grid.width,
                        grid.height
                    )
                    right_jump = self.physics.get_jump_trajectory(
                        node.x, node.y, 'right', jump_dist, jump_height, grid.width,
                        grid.height
                    )
                    self._parse_trajectory(grid, node, left_jump)
                    self._parse_trajectory(grid, node, right_jump)

    def _parse_trajectory(
        self, grid: MinimapGrid, node: MinimapNode, trajectory: list[tuple[int, int]]
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
        nodes_for_rope = trajectory[idx:idx+3]

        # connection = into_rope = None
        if max(trajectory, key=lambda i: (i[0], i[1])) == trajectory[0]:
            connection = ConnectionTypes.JUMP_LEFT
            into_rope = ConnectionTypes.JUMP_LEFT_AND_UP
        elif max(trajectory, key=lambda i: (i[0], i[1])) == trajectory[-1]:
            connection = ConnectionTypes.JUMP_RIGHT
            into_rope = ConnectionTypes.JUMP_RIGHT_AND_UP

        neighbors = grid.neighbors(node, MinimapGrid.ALL_DIAGONAL_NEIGHBORS, False)
        node_info = self.get_node_info(node)

        for x, y in trajectory:
            other_node = grid.node(x, y)
            if other_node == node or not other_node.walkable or other_node in neighbors:
                continue
            other_info = self.get_node_info(other_node)
            if other_info == node_info:
                break
            # If other node is a platform, this will stop the motion so break loop
            elif other_info.is_platform and trajectory.index((x, y)) >= apogee_idx:
                node.connect(other_node, connection)  # noqa
                break
            # If other node is ladder, we can connect to it and keep going
            elif other_info.is_ladder and (other_node.x, other_node.y) in nodes_for_rope:
                node.connect(other_node, into_rope)  # noqa


    def _add_portals(self, grid: MinimapGrid) -> None:
        for portal in self.parser.portals.res:
            source = self.parser.get_minimap_coords(portal["x"], portal["y"])
            if not grid.node(*source).walkable:
                breakpoint()

            if self.parser.map_id == portal["target_map"]:
                target_portal = self.parser.portals.get_portal(portal["target_name"])
                target = self.parser.get_minimap_coords(
                    target_portal["x"], target_portal["y"]
                )
                grid.node(*source).connect(
                    grid.node(*target), ConnectionTypes.IN_MAP_PORTAL
                )
                print(grid.node(*source))
            else:
                pass  # TODO - Connect to out-of-map portals


class MapleMap:
    """
    Class to hold the map of the game and its associated info.
    """

    def __init__(
        self, map_name: str, open_minimap_editor: bool = False, **kwargs
    ) -> None:
        self.map_name = map_name
        self.parser = MapParser(map_name)
        orig_minimap_canvas = self.parser.get_raw_minimap_grid(True)
        self.edits = MinimapEditsManager.from_json(map_name) or MinimapEditsManager()
        if open_minimap_editor:
            # This will block until the editor's mainloop is closed
            editor = MinimapEditor(
                map_name,
                orig_minimap_canvas,
                self.edits,
                include_character_position=kwargs.get(
                    "include_character_position", True
                ),
                scale=kwargs.get("scale", 5),
            )
            self.edits = editor.edits

        physics = MinimapPhysics(
            1 / self.parser.minimap_scale_x, 1 / self.parser.minimap_scale_y
        )
        self.minimap = MapleMinimap(
            self.parser, orig_minimap_canvas, self.edits, physics
        )
        # mob_ids = self.parser.get_mobs_ids()
        # self.mobs = tuple(BaseMob(mob_id) for mob_id in mob_ids)
