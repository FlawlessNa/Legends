import cv2
import numpy as np
import random

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathfinding.core.grid import Grid, DiagonalMovement
from pathfinding.core.node import GridNode
from typing import Sequence

from botting.models_abstractions import BaseMinimapFeatures
from botting.utilities import Box
from royals.interface import Minimap


class MinimapConnection:
    """
    Used by MinimapFeatures to describe how they are connected to other features.
    Connection types are:
    - "jump_down": The character can jump down from one node to another.
    - "jump_...": The character can jump from one node to another.
    - "fall": The character can fall from one node to another by walking towards the edge of a platform.
    - "jump_..._and_up": The character jumps in a direction while holding "up" key, to get into a rope/ladder.
    - "portal": The character can use a portal from one node to another (also from one map to another).
    - "teleport": The character can teleport from one node to another.
    - "flash_jump_...": The character can use flash jump to get from one node to another.
    """

    def __init__(
        self,
        other_feature_name: str | None,
        connection_type: int,
        custom_sources: list[tuple[int, int]] = None,
        custom_destinations: list[tuple[int, int]] = None,
    ):
        self.other_feature_name = other_feature_name
        self.connection_type = connection_type
        self.custom_sources = custom_sources
        self.custom_destinations = custom_destinations

        if connection_type == self.PORTAL:
            if other_feature_name is not None:
                assert (
                    custom_destinations is not None
                ), "Portal connection must have custom destinations specified."
                assert (
                    len(custom_destinations) == 1
                ), "Portal connection must have a single destination."

    def __repr__(self) -> str:
        connection_types = {
            val: key
            for key, val in self.__class__.__dict__.items()
            if isinstance(val, int)
        }
        return f"({self.other_feature_name}, {connection_types[self.connection_type]})"

    @classmethod
    def convert_to_string(cls, connection_type: int) -> str:
        connection_types = {
            val: key for key, val in cls.__dict__.items() if isinstance(val, int)
        }
        return connection_types[connection_type]

    # Class constants - Represent existing types of connections
    JUMP_DOWN = 1
    JUMP_LEFT = 2
    JUMP_RIGHT = 3
    JUMP_UP = 4
    FALL_LEFT = 5
    FALL_RIGHT = 6
    FALL_ANY = 7
    JUMP_LEFT_AND_UP = 8
    JUMP_RIGHT_AND_UP = 9
    JUMP_ANY_AND_UP = 10
    PORTAL = 11
    TELEPORT_LEFT = NotImplemented
    TELEPORT_RIGHT = NotImplemented
    TELEPORT_UP = NotImplemented
    TELEPORT_DOWN = NotImplemented
    FLASH_JUMP_LEFT = NotImplemented
    FLASH_JUMP_RIGHT = NotImplemented


@dataclass
class MinimapNode(GridNode):
    """
    Class representing a node in the pathfinding algorithm.
    Each MinimapNode is a point within a feature the minimap.
    Minimap Nodes have additional properties with respect to their "connections" to other nodes.
    Their type of connection describes how the connection can be used in-game.
    """

    connections_types: list = field(default_factory=list, init=False)

    def connect(self, node: "MinimapNode", connection_type: int) -> None:
        """
        Connects the current node to another node.
        :param node: Node to connect to.
        :param connection_type: The type of connection between the other node. "jump_down", "jump", "teleport", or "portal".
        :return:
        """
        super().connect(node)
        self.connections_types.append(connection_type)


class MinimapGrid(Grid):
    """
    Exactly the same as the Grid class, except that it uses MinimapNodes instead of GridNodes.
    Weights between nodes are also calculated differently for connections.
    Special treatment of TELEPORT connections depending on whether they are allowed or not.
    """

    nodes: list[list[MinimapNode]]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._replace_nodes()
        self.allow_teleport = None

    def node(self, x, y) -> MinimapNode:
        """
        get node at position
        :param x: x pos
        :param y: y pos
        :return:
        """
        return self.nodes[y][x]

    def calc_cost(self, node_a: MinimapNode, node_b: MinimapNode, weighted=False):
        """
        Get the cost between neighbor nodes.
        If the nodes are neighbors through a connection, add the horizontal distance
        into the cost. This avoids unnecessary jumps on platforms/ropes and such.
        """
        ng = super().calc_cost(node_a, node_b, weighted)
        if node_a.connections and node_b in node_a.connections:
            dx = abs(node_a.x - node_b.x)
            ng += dx
        return ng

    def neighbors(
        self, node: MinimapNode,
        diagonal_movement: DiagonalMovement = DiagonalMovement.never
    ) -> list[GridNode]:
        """
        Same as original Grid, but removes TELEPORT connections if not allowed.
        """
        assert isinstance(self.allow_teleport, bool), "Must set allow_teleport before calling neighbors."
        neighbors = super().neighbors(node, diagonal_movement)
        result = neighbors.copy()
        if not self.allow_teleport:
            for neighbor in neighbors:
                if node.connections and neighbor in node.connections:
                    if node.connections_types[node.connections.index(neighbor)] in [
                        MinimapConnection.TELEPORT_UP,
                        MinimapConnection.TELEPORT_DOWN,
                        MinimapConnection.TELEPORT_LEFT,
                        MinimapConnection.TELEPORT_RIGHT
                    ]:
                        result.remove(neighbor)
        return result

    def _replace_nodes(self):
        for y, row in enumerate(self.nodes):
            for x, node in enumerate(row):
                self.nodes[y][x] = MinimapNode(
                    node.x,
                    node.y,
                    node.walkable,
                    node.weight,
                    node.grid_id,
                    node.connections,
                )


@dataclass(frozen=True, kw_only=True)
class MinimapFeature(Box):
    """
    Class representing a feature on the minimap.
    A minimap feature is essentially a box representing the platform coordinates on the minimap.
    As opposed to a Box, a MinimapFeature must have a name and either its width or its height must be equal to 0.
    MinimapFeatures establish connections with other MinimapFeatures, through various types of connections.
    Each "point" within a MinimapFeature is considered a "MinimapNode" in the pathfinding algorithm.
    MinimapFeature are iterables - iterating over them will return all the nodes within the feature.
    """

    name: str
    connections: list[MinimapConnection] = field(default_factory=list)
    central_node: tuple[int, int] = field(default=None)
    area_coverage: float = field(default=0.9)
    randomized_edge: int = field(default=5)

    def __post_init__(self):
        super().__post_init__()
        assert (
            self.width == 0 or self.height == 0
        ), "Minimap Features should be 1-dimensional"

    @property
    def is_platform(self) -> bool:
        return self.height == 0

    @property
    def is_ladder(self) -> bool:
        return self.width == 0

    @property
    def left_edge(self) -> tuple[int, int]:
        rand_buffer = random.randint(0, self.randomized_edge)
        return (
            max(
                int(
                    rand_buffer + self.left + self.width * (1 - self.area_coverage) / 2
                ),
                self.left,
            ),
            self.top,
        )

    @property
    def right_edge(self) -> tuple[int, int]:
        rand_buffer = random.randint(-self.randomized_edge, 0)
        return (
            min(
                int(
                    rand_buffer + self.right - self.width * (1 - self.area_coverage) / 2
                ),
                self.right,
            ),
            self.top,
        )

    @property
    def area(self) -> int:
        """
        Overwrites default behavior and considers the axis with 0 length equal to 1 for this calculation.
        """
        return max(self.width, self.height)

    def __iter__(self):
        """
        Iterates over all nodes within the feature.
        :return:
        """
        if self.is_platform:
            for x in range(self.left, self.right + 1):
                yield x, self.top
        elif self.is_ladder:
            for y in range(self.top, self.bottom + 1):
                yield self.left, y
        else:
            raise NotImplementedError("Should not reach this point")


class MinimapPathingMechanics(BaseMinimapFeatures, Minimap, ABC):
    minimap_speed: float
    jump_height: int
    jump_distance: int
    jump_down_limit: int = (
        500  # No limit by default (500 px is extremely large, will never be reached)
    )
    teleport_h_dist: int  # Horizontal distance of teleport
    teleport_v_up_dist: int  # Vertical distance of teleport (upwards)
    teleport_v_down_dist: int  # Vertical distance of teleport (downwards)

    @property
    @abstractmethod
    def feature_cycle(self) -> list[MinimapFeature]:
        """
        Returns a list of the features to be cycled through. This is used for smarter
        map rotations.
        :return:
        """
        pass

    def __init__(self):
        for feature in self.features.values():
            if feature.connections:
                assert all(
                    conn.other_feature_name in self.features
                    for conn in feature.connections
                    if conn.other_feature_name is not None
                ), "Invalid connection names."

        self.grid = self.generate_grid_template()

    def set_teleport_allowed(self, allow_teleport: bool):
        self.grid.allow_teleport = allow_teleport

    def jump_parabola_y(self, x):
        h, k = self.jump_distance / 2, self.jump_height
        a = k / h**2
        return -a * (x - h) ** 2 + k

    def _jump_trajectory(
        self, starting_point: tuple[int, int], direction: str, fall_only: bool = False
    ):
        """
        Computes the trajectory of a jump in the specified direction.
        :param starting_point: Starting point of the trajectory.
        :param direction: Direction of the trajectory. Can be "left" or "right".
        :return: List of points representing the trajectory.
        """
        assert direction in ["left", "right"], "Invalid direction for trajectory."
        x_values = np.arange(starting_point[0], self.map_area_width, 0.1)

        if fall_only:
            y_values = (
                starting_point[1]
                - self.jump_parabola_y(
                    x_values - starting_point[0] + self.jump_distance / 2
                )
                + self.jump_height
            )
        else:
            y_values = starting_point[1] - self.jump_parabola_y(
                x_values - starting_point[0]
            )
        if direction == "left":
            x_values = np.linspace(
                starting_point[0],
                starting_point[0] - (x_values[-1] - starting_point[0]),
                len(y_values),
            )

        # Now truncate the arrays such that they only contain points within the map area
        mask = (
            (x_values >= 0)
            & (x_values <= self.map_area_width)
            & (y_values >= 0)
            & (y_values <= self.map_area_height)
        )
        x_values = x_values[mask].astype(int)
        y_values = y_values[mask].astype(int)

        # The rounding may cause adjacent cells to be only connected diagonally. Add buffer in such cases.
        buffered_x_values = []
        buffered_y_values = []
        for i in range(len(x_values) - 1):
            buffered_x_values.append(x_values[i])
            buffered_y_values.append(y_values[i])
            dx = x_values[i + 1] - x_values[i]
            dy = y_values[i + 1] - y_values[i]
            if abs(dx) == abs(dy) == 1:
                buffered_x_values.append(x_values[i] + np.sign(dx))
                buffered_y_values.append(y_values[i])
                buffered_x_values.append(x_values[i])
                buffered_y_values.append(y_values[i] + np.sign(dy))
        buffered_x_values.append(x_values[-1])
        buffered_y_values.append(y_values[-1])
        x_values = np.array(buffered_x_values)
        y_values = np.array(buffered_y_values)

        return sorted(
            set(zip(x_values, y_values)), key=list(zip(x_values, y_values)).index
        )

    def _preprocess_img(self, image: np.ndarray) -> np.ndarray:
        """
        Creates a Grid-like image used for pathfinding algorithm.
        :param image: Original minimap area image.
        :return: Binary image with white pixels representing walkable areas.
        """
        if len(image.shape) == 3:
            image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        canvas = np.zeros_like(image)
        for feature in self.features.values():
            pt1: Sequence = (feature.left, feature.top)
            pt2: Sequence = (feature.right, feature.bottom)
            cv2.line(canvas, pt1, pt2, (255, 255, 255), 1)

        return canvas

    @property
    def features(self) -> dict[str, MinimapFeature]:
        """
        Returns a dictionary of all the features of the map.
        This overwrites the default behavior that returns all "box" class attributes.
        :return:
        """
        return {
            feat.name: feat
            for feat in self.__class__.__dict__.values()
            if isinstance(feat, MinimapFeature)
        }

    def generate_grid_template(self) -> MinimapGrid:
        """
        Generates a "grid"-like array of the minimap, which includes royals mechanics.
        Those mechanics are:
            - Connect nodes between parallel, horizontal platforms, provided they are not too distant (jump up/down/left/right/FALL).
            - Connect adjacent nodes with small gaps (jump and/or teleport), provided they are not too distant.
            - Connect nodes between ladders and platforms and vice-versa
            - Connect nodes between portals (can be one-way or two-way) # TODO
        :return: Grid object
        """
        width, height = self.map_area_width, self.map_area_height
        canvas = np.zeros((height, width), dtype=np.uint8)
        canvas = self._preprocess_img(canvas)

        base_grid = MinimapGrid(matrix=np.where(canvas == 255, 1, 0))

        for feature in self.features.values():
            if feature.connections:
                # TODO - Add custom connections defined by the feature itself
                breakpoint()

            for node in feature:
                # Build default connections from 'standard' mechanics
                if feature.is_platform:
                    self._add_vertical_connection(base_grid, node, MinimapConnection.JUMP_UP)
                    self._add_vertical_connection(base_grid, node, MinimapConnection.JUMP_DOWN)
                    self._add_vertical_connection(base_grid, node, MinimapConnection.TELEPORT_UP)
                    self._add_vertical_connection(base_grid, node, MinimapConnection.TELEPORT_DOWN)
                    # Check for JUMP_UP connection by finding the closest walkable node above current one, if any
                    for other_node in (
                        base_grid.node(node[0], y)
                        for y in range(node[1] - 1, node[1] - self.jump_height - 1, -1)
                    ):
                        if other_node.walkable:
                            other_feature = self.get_feature_containing(
                                (other_node.x, other_node.y)
                            )
                            if not other_feature.is_ladder:
                                base_grid.node(*node).connect(
                                    base_grid.node(other_node.x, other_node.y),
                                    MinimapConnection.JUMP_UP,
                                )

                    # Check for JUMP_DOWN connection by finding the closest walkable node below current one, if any
                    for other_node in (
                        base_grid.node(node[0], y)
                        for y in range(
                            node[1] + 1,
                            min(
                                node[1] + self.jump_down_limit + 1, self.map_area_height
                            ),
                        )
                    ):
                        if other_node.walkable:
                            base_grid.node(*node).connect(
                                base_grid.node(other_node.x, other_node.y),
                                MinimapConnection.JUMP_DOWN,
                            )
                            break  # Only add one connection (the closest)

                    # Compute jump trajectories for both directions
                    left_trajectory = self._jump_trajectory(node, "left")
                    right_trajectory = self._jump_trajectory(node, "right")
                    self._parse_trajectory(
                        node,
                        feature,
                        left_trajectory,
                        MinimapConnection.JUMP_LEFT,
                        MinimapConnection.JUMP_LEFT_AND_UP,
                        base_grid,
                    )
                    self._parse_trajectory(
                        node,
                        feature,
                        right_trajectory,
                        MinimapConnection.JUMP_RIGHT,
                        MinimapConnection.JUMP_RIGHT_AND_UP,
                        base_grid,
                    )

                    # Check for FALL_LEFT connection
                    if node == (feature.left, feature.top):
                        left_trajectory = self._jump_trajectory(
                            node, "left", fall_only=True
                        )
                        self._parse_trajectory(
                            node,
                            feature,
                            left_trajectory,
                            MinimapConnection.FALL_LEFT,
                            MinimapConnection.FALL_LEFT,
                            base_grid,
                        )  # TODO - Add FALL_LEFT_AND_UP if needed

                    # Check for FALL_RIGHT connection
                    if node == (feature.right, feature.top):
                        right_trajectory = self._jump_trajectory(
                            node, "right", fall_only=True
                        )
                        self._parse_trajectory(
                            node,
                            feature,
                            right_trajectory,
                            MinimapConnection.FALL_RIGHT,
                            MinimapConnection.FALL_RIGHT,
                            base_grid,
                        )  # TODO - Add FALL_RIGHT_AND_UP if needed

                elif feature.is_ladder:
                    # Skip the node on top to make sure jumping out of it doesn't lead back to platform at top (if any)
                    if node[1] == feature.top or node[1] == feature.bottom:
                        continue

                    # Compute jump trajectories for both directions
                    left_trajectory = self._jump_trajectory(
                        node, "left", fall_only=True
                    )
                    self._parse_trajectory(
                        node,
                        feature,
                        left_trajectory,
                        MinimapConnection.JUMP_LEFT,
                        MinimapConnection.JUMP_LEFT_AND_UP,
                        base_grid,
                    )

                    right_trajectory = self._jump_trajectory(
                        node, "right", fall_only=True
                    )
                    self._parse_trajectory(
                        node,
                        feature,
                        right_trajectory,
                        MinimapConnection.JUMP_RIGHT,
                        MinimapConnection.JUMP_RIGHT_AND_UP,
                        base_grid,
                    )

        return base_grid

    def _parse_trajectory(
        self,
        node: tuple[int, int],
        feature: MinimapFeature,
        trajectory: list[tuple[int, int]],
        connection_type_platform: int,
        connection_type_ladder: int,
        grid: MinimapGrid,
    ):
        """
        Parses a trajectory and adds connections to the grid.
        :param node: Starting point of the trajectory.
        :param trajectory: List of points representing the trajectory.
        :param grid: Grid to add connections to.
        :return:
        """
        for other_node in trajectory:
            if not grid.node(*other_node).walkable:
                continue
            elif other_node == node:
                continue
            # TODO - refactor using grid.neighbors
            elif feature.is_platform and (
                other_node[1] == node[1] and abs(other_node[0] - node[0]) <= 1
            ):
                continue
            elif feature.is_ladder and (
                other_node[0] == node[0] and abs(other_node[1] - node[1]) <= 1
            ):
                continue
            else:
                other_feature = self.get_feature_containing(other_node)
                if other_feature != feature:
                    # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                    if other_feature.is_platform:
                        grid.node(*node).connect(
                            grid.node(*other_node),
                            connection_type_platform,
                        )
                        break
                    # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                    elif other_feature.is_ladder:
                        grid.node(*node).connect(
                            grid.node(*other_node), connection_type_ladder
                        )
                        # Also add the horizontal distance as weight to the ladder
                        grid.node(*other_node).weight = abs(other_node[0] - node[0])
                else:
                    break
