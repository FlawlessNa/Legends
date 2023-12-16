import cv2
import numpy as np

from abc import ABC
from dataclasses import dataclass, field
from pathfinding.core.grid import Grid
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
            val: key
            for key, val in cls.__dict__.items()
            if isinstance(val, int)
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
    """

    nodes: list[list[MinimapNode]]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._replace_nodes()

    def node(self, x, y) -> MinimapNode:
        """
        get node at position
        :param x: x pos
        :param y: y pos
        :return:
        """
        return self.nodes[y][x]

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
    jump_down_limit: int = 500  # No limit by default (500 is extremely large, will never be reached)

    def __init__(self):
        for feature in self.features.values():
            if feature.connections:
                assert all(
                    conn.other_feature_name in self.features
                    for conn in feature.connections
                    if conn.other_feature_name is not None
                ), "Invalid connection names."

        # Compute a "parabola"-like equation to help in establishing connections
        h, k = self.jump_distance / 2, self.jump_height
        a = k / h ** 2
        self.jump_parabola_y = lambda x: - a * (x - h) ** 2 + k
        self.jump_parabola_x1 = lambda y: h + np.sqrt(-(y - k) / a)  # Two solutions
        self.jump_parabola_x2 = lambda y: h - np.sqrt(-(y - k) / a)  # Two solutions

        self.grid = self.generate_grid_template()

    def _jump_trajectory(self, starting_point: tuple[int, int], direction: str, fall_only: bool = False):
        """
        Computes the trajectory of a jump in the specified direction.
        :param starting_point: Starting point of the trajectory.
        :param direction: Direction of the trajectory. Can be "left" or "right".
        :return: List of points representing the trajectory.
        """
        assert direction in ["left", "right"], "Invalid direction for trajectory."
        x_values = np.arange(starting_point[0], self.map_area_width, 0.1)

        if fall_only:
            y_values = starting_point[1] - self.jump_parabola_y(x_values - starting_point[0] + self.jump_distance / 2) + self.jump_height
        else:
            y_values = starting_point[1] - self.jump_parabola_y(x_values - starting_point[0])
        if direction == "left":
            x_values = np.linspace(starting_point[0], starting_point[0] - (x_values[-1] - starting_point[0]), len(y_values))

        # Now truncate the arrays such that they only contain points within the map area
        mask = (x_values >= 0) & (x_values <= self.map_area_width) & (y_values >= 0) & (y_values <= self.map_area_height)
        x_values = x_values[mask].astype(int)
        y_values = y_values[mask].astype(int)

        # The rounding may cause adjacent cells to be only connected diagonally. Add buffer in such cases.
        buffered_x_values = []
        buffered_y_values = []
        for i in range(len(x_values)-1):
            buffered_x_values.append(x_values[i])
            buffered_y_values.append(y_values[i])
            dx = x_values[i+1] - x_values[i]
            dy = y_values[i+1] - y_values[i]
            if abs(dx) == abs(dy) == 1:
                buffered_x_values.append(x_values[i] + np.sign(dx))
                buffered_y_values.append(y_values[i])
                buffered_x_values.append(x_values[i])
                buffered_y_values.append(y_values[i] + np.sign(dy))
        buffered_x_values.append(x_values[-1])
        buffered_y_values.append(y_values[-1])
        x_values = np.array(buffered_x_values)
        y_values = np.array(buffered_y_values)

        return sorted(set(zip(x_values, y_values)), key=list(zip(x_values, y_values)).index)

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

                    # Check for JUMP_UP connection by finding the closest walkable node above current one, if any
                    for other_node in (base_grid.node(node[0], y) for y in range(node[1] - 1, node[1] - self.jump_height - 1, -1)):
                        if other_node.walkable:
                            base_grid.node(*node).connect(base_grid.node(other_node.x, other_node.y), MinimapConnection.JUMP_UP)

                    # Check for JUMP_DOWN connection by finding the closest walkable node below current one, if any
                    for other_node in (base_grid.node(node[0], y) for y in range(node[1] + 1, min(node[1] + self.jump_down_limit, self.map_area_height))):
                        if other_node.walkable:
                            base_grid.node(*node).connect(base_grid.node(other_node.x, other_node.y), MinimapConnection.JUMP_DOWN)
                            break  # Only add one connection (the closest)

                    # Compute jump trajectories for both directions
                    left_trajectory = self._jump_trajectory(node, "left")
                    right_trajectory = self._jump_trajectory(node, "right")

                    # For each direction, check intersection with other features and establish connection, if any
                    for other_node in left_trajectory:
                        if not base_grid.node(*other_node).walkable:
                            continue
                        else:
                            other_feature = self.get_feature_containing(other_node)
                            if other_feature != feature:
                                # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                                if other_feature.is_platform:
                                    base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_LEFT)
                                    break
                                # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                                elif other_feature.is_ladder:
                                    base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_LEFT_AND_UP)

                    for other_node in right_trajectory:
                        if not base_grid.node(*other_node).walkable:
                            continue
                        else:
                            other_feature = self.get_feature_containing(other_node)
                            if other_feature != feature:
                                # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                                if other_feature.is_platform:
                                    base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_RIGHT)
                                    break
                                # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                                elif other_feature.is_ladder:
                                    base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_RIGHT_AND_UP)

                    # Check for FALL_LEFT connection
                    if node == (feature.left, feature.top):
                        left_trajectory = self._jump_trajectory(node, "left", fall_only=True)
                        for other_node in left_trajectory:
                            if not base_grid.node(*other_node).walkable:
                                continue
                            else:
                                other_feature = self.get_feature_containing(other_node)
                                # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                                if other_feature.is_platform:
                                    base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.FALL_LEFT)
                                    break
                                # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                                elif other_feature.is_ladder:
                                    # TODO - If every needed, add a "FALL_LEFT_AND_UP" connection
                                    pass

                    # Check for FALL_RIGHT connection
                    if node == (feature.right, feature.top):
                        right_trajectory = self._jump_trajectory(node, "right", fall_only=True)
                        for other_node in right_trajectory:
                            if not base_grid.node(*other_node).walkable:
                                continue
                            else:
                                other_feature = self.get_feature_containing(other_node)
                                # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                                if other_feature.is_platform:
                                    base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.FALL_RIGHT)
                                    break
                                # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                                elif other_feature.is_ladder:
                                    # TODO - If every needed, add a "FALL_RIGHT_AND_UP" connection
                                    pass

                elif feature.is_ladder:
                    # Skip the node on top to make sure jumping out of it doesnt lead back to platform at top (if any)
                    if node[1] == feature.top:
                        continue

                    # Compute jump trajectories for both directions
                    left_trajectory = self._jump_trajectory(node, "left", fall_only=True)
                    for other_node in left_trajectory:
                        if not base_grid.node(*other_node).walkable:
                            continue
                        else:
                            other_feature = self.get_feature_containing(other_node)
                            # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                            if other_feature.is_platform:
                                base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_LEFT)
                                break
                            # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                            elif other_feature.is_ladder:
                                base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_LEFT_AND_UP)
#
                    right_trajectory = self._jump_trajectory(node, "right", fall_only=True)
                    for other_node in right_trajectory:
                        if not base_grid.node(*other_node).walkable:
                            continue
                        else:
                            other_feature = self.get_feature_containing(other_node)
                            # If the other feature is a platform, the rest of the trajectory is ignored as this stops the movement
                            if other_feature.is_platform:
                                base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_RIGHT)
                                break
                            # If it's a ladder, we keep checking the remainder as the ladder can be bypassed
                            elif other_feature.is_ladder:
                                base_grid.node(*node).connect(base_grid.node(*other_node), MinimapConnection.JUMP_RIGHT_AND_UP)
# #------------------------------------------------------- Original (below)-------------------------------------------------------#
#             #
#             # for connection in feature.connections:
#             #     if connection.other_feature_name is None:
#             #         continue  # TODO: Implement connections to other maps
#             #     other_feature = self.features[connection.other_feature_name]
#             #
#             #     if connection.connection_type == MinimapConnection.JUMP_DOWN:
#             #         self._add_jump_down_connection(base_grid, feature, other_feature)
#             #
#             #     elif connection.connection_type == MinimapConnection.JUMP_LEFT:
#             #         self._add_jump_connection(base_grid, "left", feature, other_feature)
#             #
#             #     elif connection.connection_type == MinimapConnection.JUMP_RIGHT:
#             #         self._add_jump_connection(
#             #             base_grid, "right", feature, other_feature
#             #         )
#             #
#             #     elif connection.connection_type == MinimapConnection.JUMP_UP:
#             #         self._add_jump_up_connection(base_grid, feature, other_feature)
#             #
#             #     elif connection.connection_type == MinimapConnection.FALL_LEFT:
#             #         self._add_fall_connection(base_grid, "left", feature, other_feature)
#             #
#             #     elif connection.connection_type == MinimapConnection.FALL_RIGHT:
#             #         self._add_fall_connection(
#             #             base_grid, "right", feature, other_feature
#             #         )
#             #
#             #     elif connection.connection_type == MinimapConnection.FALL_ANY:
#             #         self._add_fall_connection(base_grid, "left", feature, other_feature)
#             #         self._add_fall_connection(
#             #             base_grid, "right", feature, other_feature
#             #         )
#             #
#             #     elif connection.connection_type == MinimapConnection.JUMP_LEFT_AND_UP:
#             #         self._add_jump_into_ladder_connection(
#             #             base_grid, "left", feature, other_feature
#             #         )
#             #
#             #     elif connection.connection_type == MinimapConnection.JUMP_RIGHT_AND_UP:
#             #         self._add_jump_into_ladder_connection(
#             #             base_grid, "right", feature, other_feature
#             #         )
#             #
#             #     elif connection.connection_type == MinimapConnection.JUMP_ANY_AND_UP:
#             #         self._add_jump_into_ladder_connection(
#             #             base_grid, "left", feature, other_feature
#             #         )
#             #         self._add_jump_into_ladder_connection(
#             #             base_grid, "right", feature, other_feature
#             #         )
#             #
#             #     elif connection.connection_type == MinimapConnection.PORTAL:
#             #         sources = (
#             #             connection.custom_sources
#             #             if connection.custom_sources is not None
#             #             else [
#             #                 (i, feature.top)
#             #                 for i in range(feature.left, feature.right + 1)
#             #             ]
#             #         )
#             #         self._add_portal_connection(
#             #             base_grid,
#             #             sources,
#             #             connection.custom_destinations,
#             #         )
#             #     else:
#             #         breakpoint()
#             #         raise NotImplementedError("Should not reach this point")
#
#         return base_grid
#
#     @staticmethod
#     def _add_jump_down_connection(
#         grid: MinimapGrid, feature: MinimapFeature, other_feature: MinimapFeature
#     ) -> None:
#         """
#         Adds connections between each vertically parallel nodes between the two features, but only if there are no walkable
#         nodes in between them.
#         # TODO - See if custom behavior needed, for example for platforms where jumping down is only partially possible.
#         """
#
#         for node in range(feature.left, feature.right + 1):
#             if node in range(
#                 other_feature.left, other_feature.right + 1
#             ):  # Make sure nodes are vertically aligned
#                 if not any(
#                     grid.node(node, y).walkable
#                     for y in range(feature.top + 1, other_feature.top)
#                 ):  # Make sure there are no walkable nodes in between
#                     grid.node(node, feature.top).connect(
#                         grid.node(node, other_feature.top),
#                         connection_type=MinimapConnection.JUMP_DOWN,
#                     )
#
#     @staticmethod
#     def _add_jump_up_connection(
#         grid: MinimapGrid, feature: MinimapFeature, other_feature: MinimapFeature
#     ) -> None:
#         """
#         Adds connections between each vertically parallel nodes between the two features, but only if there are no walkable
#         nodes in between them. Reversed order compared to jump down.
#         # TODO - See if custom behavior needed, for example for platforms where jumping down is only partially possible.
#         """
#
#         for node in range(feature.left, feature.right + 1):
#             if node in range(
#                 other_feature.left, other_feature.right + 1
#             ):  # Make sure nodes are vertically aligned
#                 if not any(
#                     grid.node(node, y).walkable
#                     for y in range(other_feature.top + 1, feature.top)
#                 ):  # Make sure there are no walkable nodes in between
#                     grid.node(node, feature.top).connect(
#                         grid.node(node, other_feature.top),
#                         connection_type=MinimapConnection.JUMP_UP,
#                     )
#
#     @staticmethod
#     def _add_jump_connection(
#         grid: MinimapGrid,
#         direction: str,
#         feature: MinimapFeature,
#         other_feature: MinimapFeature,
#         horizontal_distance: int = 5,
#     ) -> None:
#         """
#         If feature is a platform, adds connections between endpoints of both features.
#         If feature is a ladder, adds a connection between each point in the ladder and the other feature with the horizontal distance.
#         Weights are added to limit jumps when possible.
#         # TODO - See if custom behavior needed, for example for platforms where jumping down is only partially possible.
#         """
#         assert direction in ["left", "right"], "Invalid direction for jump connection."
#         connection_type = (
#             MinimapConnection.JUMP_LEFT
#             if direction == "left"
#             else MinimapConnection.JUMP_RIGHT
#         )
#         if feature.height == 0:
#             feature_end = feature.left if direction == "left" else feature.right
#             other_feature_end = (
#                 other_feature.right if direction == "left" else other_feature.left
#             )
#             grid.node(feature_end, feature.top).connect(
#                 grid.node(other_feature_end, other_feature.top),
#                 connection_type=connection_type,
#             )
#             grid.node(feature_end, feature.top).weight = abs(
#                 feature_end - other_feature_end
#             )
#         elif feature.width == 0:
#             # Jumping out of a ladder
#             other_feature_end = (
#                 feature.left - horizontal_distance
#                 if direction == "left"
#                 else feature.right + horizontal_distance
#             )
#             # Don't connect the first nodes as the character may not be able to actually jump down the ladder from there
#             for node in range(feature.top + 2, feature.bottom):
#                 grid.node(feature.left, node).connect(
#                     grid.node(other_feature_end, other_feature.top),
#                     connection_type=connection_type,
#                 )
#                 # No need to add weight on ladders as its very easy to jump down from them
#                 # grid.node(feature.left, node).weight = (
#                 #     abs(feature.left - other_feature_end) + 1
#                 # )
#
#     @staticmethod
#     def _add_fall_connection(
#         grid: MinimapGrid,
#         direction: str,
#         feature: MinimapFeature,
#         other_feature: MinimapFeature,
#         horizontal_distance: int = 5,
#     ) -> None:
#         """
#         Adds connections between endpoints of the feature and points of the other feature a certain horizontal
#         distance from those endpoints.
#         """
#         assert direction in ["left", "right"], "Invalid direction for fall connection."
#         connection_type = (
#             MinimapConnection.FALL_LEFT
#             if direction == "left"
#             else MinimapConnection.FALL_RIGHT
#         )
#         feature_end = feature.left if direction == "left" else feature.right
#         other_feature_pt = (
#             feature_end + horizontal_distance
#             if direction == "right"
#             else feature_end - horizontal_distance
#         )
#         grid.node(feature_end, feature.top).connect(
#             grid.node(other_feature_pt, other_feature.top),
#             connection_type=connection_type,
#         )
#
#     @staticmethod
#     def _add_portal_connection(
#         grid: MinimapGrid,
#         source_nodes: list[tuple[int, int]],
#         target_node: list[tuple[int, int]],
#     ) -> None:
#         """
#         Adds connections between nodes into the grid based on portals in-game.
#         Weight is left unchanged (No extra cost to use portals; in most cases its.
#         """
#         assert len(target_node) == 1, "Portal target must be a single node."
#         target_node = target_node[0]
#         for source in source_nodes:
#             grid.node(*source).connect(
#                 grid.node(*target_node), connection_type=MinimapConnection.PORTAL
#             )
#
#     @staticmethod
#     def _add_jump_into_ladder_connection(
#         grid: MinimapGrid,
#         direction: str,
#         feature: MinimapFeature,
#         other_feature: MinimapFeature,
#         jump_horizontal_distance: int = 3,
#         jump_vertical_distance: int = 4,
#     ) -> None:
#         """
#         Adds connections between nodes into the grid based on jump into ladder in-game.
#         # TODO - Change if custom nodes are needed here.
#         """
#         assert (
#             feature.height == 0 and other_feature.width == 0
#         ), "Invalid features for jump into ladder."
#         assert direction in [
#             "left",
#             "right",
#         ], "Invalid direction for jump into ladder."
#         horizontal_distance = (
#             -jump_horizontal_distance
#             if direction == "right"
#             else jump_horizontal_distance
#         )
#         connection_type = (
#             MinimapConnection.JUMP_RIGHT_AND_UP
#             if direction == "right"
#             else MinimapConnection.JUMP_LEFT_AND_UP
#         )
#
#         grid.node(other_feature.left + horizontal_distance, feature.top).connect(
#             grid.node(other_feature.left, feature.top - jump_vertical_distance),
#             connection_type=connection_type,
#         )
