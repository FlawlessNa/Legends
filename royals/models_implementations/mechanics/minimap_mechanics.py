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
    """

    name: str
    connections: list[MinimapConnection] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        assert (
            self.width == 0 or self.height == 0
        ), "Minimap Features should be 1-dimensional"

    @property
    def area(self) -> int:
        """
        Overwrites default behavior and considers the axis with 0 length equal to 1 for this calculation.
        """
        return max(self.width, self.height)


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
        self.grid = self.generate_grid_template()

        # Compute a "parabola"-like equation to help in establishing connections
        h, k = self.jump_distance / 2, self.jump_height
        a = -k / h ** 2

        self.jump_parabola_y = lambda x: - a * (x - h) ** 2 + k
        self.jump_parabola_x = lambda y: h + np.sqrt(-(y - k) / a)  # Two solutions

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
            - Connect nodes between parallel, horizontal platforms, provided they are not too distant (jump down).
            - Connect adjacent nodes with small gaps (jump and/or teleport), provided they are not too distant.
            - Connect nodes between teleporters (can be one-way or two-way).
            - Connect nodes between portals (can be one-way or two-way) # TODO
        :return: Grid object
        """
        width, height = self.map_area_width, self.map_area_height
        canvas = np.zeros((height, width), dtype=np.uint8)
        canvas = self._preprocess_img(canvas)

        base_grid = MinimapGrid(matrix=np.where(canvas == 255, 1, 0))

        for feature in self.features.values():
            for other_feature in self.features.values():
                if feature == other_feature:
                    continue
                if other_feature.name in [conn.other_feature_name for conn in feature.connections]:
                    # TODO -- Special connections not constructed by default, add custom-built ones here
                    pass

                if feature.height == other_feature.height == 0:
                    # Both are platforms
                    vertical_distance = feature.top - other_feature.top
                    if 0 < vertical_distance <= self.jump_down_limit:
                        # Current Feature above the other - add potential jump down connections
                        self._add_jump_down_connection(base_grid, feature, other_feature)
                    elif 0 < -vertical_distance <= self.jump_height:
                        # Current Feature below the other - add potential jump up connections
                        self._add_jump_up_connection(base_grid, feature, other_feature)


            #
            # for connection in feature.connections:
            #     if connection.other_feature_name is None:
            #         continue  # TODO: Implement connections to other maps
            #     other_feature = self.features[connection.other_feature_name]
            #
            #     if connection.connection_type == MinimapConnection.JUMP_DOWN:
            #         self._add_jump_down_connection(base_grid, feature, other_feature)
            #
            #     elif connection.connection_type == MinimapConnection.JUMP_LEFT:
            #         self._add_jump_connection(base_grid, "left", feature, other_feature)
            #
            #     elif connection.connection_type == MinimapConnection.JUMP_RIGHT:
            #         self._add_jump_connection(
            #             base_grid, "right", feature, other_feature
            #         )
            #
            #     elif connection.connection_type == MinimapConnection.JUMP_UP:
            #         self._add_jump_up_connection(base_grid, feature, other_feature)
            #
            #     elif connection.connection_type == MinimapConnection.FALL_LEFT:
            #         self._add_fall_connection(base_grid, "left", feature, other_feature)
            #
            #     elif connection.connection_type == MinimapConnection.FALL_RIGHT:
            #         self._add_fall_connection(
            #             base_grid, "right", feature, other_feature
            #         )
            #
            #     elif connection.connection_type == MinimapConnection.FALL_ANY:
            #         self._add_fall_connection(base_grid, "left", feature, other_feature)
            #         self._add_fall_connection(
            #             base_grid, "right", feature, other_feature
            #         )
            #
            #     elif connection.connection_type == MinimapConnection.JUMP_LEFT_AND_UP:
            #         self._add_jump_into_ladder_connection(
            #             base_grid, "left", feature, other_feature
            #         )
            #
            #     elif connection.connection_type == MinimapConnection.JUMP_RIGHT_AND_UP:
            #         self._add_jump_into_ladder_connection(
            #             base_grid, "right", feature, other_feature
            #         )
            #
            #     elif connection.connection_type == MinimapConnection.JUMP_ANY_AND_UP:
            #         self._add_jump_into_ladder_connection(
            #             base_grid, "left", feature, other_feature
            #         )
            #         self._add_jump_into_ladder_connection(
            #             base_grid, "right", feature, other_feature
            #         )
            #
            #     elif connection.connection_type == MinimapConnection.PORTAL:
            #         sources = (
            #             connection.custom_sources
            #             if connection.custom_sources is not None
            #             else [
            #                 (i, feature.top)
            #                 for i in range(feature.left, feature.right + 1)
            #             ]
            #         )
            #         self._add_portal_connection(
            #             base_grid,
            #             sources,
            #             connection.custom_destinations,
            #         )
            #     else:
            #         breakpoint()
            #         raise NotImplementedError("Should not reach this point")

        return base_grid

    @staticmethod
    def _add_jump_down_connection(
        grid: MinimapGrid, feature: MinimapFeature, other_feature: MinimapFeature
    ) -> None:
        """
        Adds connections between each vertically parallel nodes between the two features, but only if there are no walkable
        nodes in between them.
        # TODO - See if custom behavior needed, for example for platforms where jumping down is only partially possible.
        """

        for node in range(feature.left, feature.right + 1):
            if node in range(
                other_feature.left, other_feature.right + 1
            ):  # Make sure nodes are vertically aligned
                if not any(
                    grid.node(node, y).walkable
                    for y in range(feature.top + 1, other_feature.top)
                ):  # Make sure there are no walkable nodes in between
                    grid.node(node, feature.top).connect(
                        grid.node(node, other_feature.top),
                        connection_type=MinimapConnection.JUMP_DOWN,
                    )

    @staticmethod
    def _add_jump_up_connection(
        grid: MinimapGrid, feature: MinimapFeature, other_feature: MinimapFeature
    ) -> None:
        """
        Adds connections between each vertically parallel nodes between the two features, but only if there are no walkable
        nodes in between them. Reversed order compared to jump down.
        # TODO - See if custom behavior needed, for example for platforms where jumping down is only partially possible.
        """

        for node in range(feature.left, feature.right + 1):
            if node in range(
                other_feature.left, other_feature.right + 1
            ):  # Make sure nodes are vertically aligned
                if not any(
                    grid.node(node, y).walkable
                    for y in range(other_feature.top + 1, feature.top)
                ):  # Make sure there are no walkable nodes in between
                    grid.node(node, feature.top).connect(
                        grid.node(node, other_feature.top),
                        connection_type=MinimapConnection.JUMP_UP,
                    )

    @staticmethod
    def _add_jump_connection(
        grid: MinimapGrid,
        direction: str,
        feature: MinimapFeature,
        other_feature: MinimapFeature,
        horizontal_distance: int = 5,
    ) -> None:
        """
        If feature is a platform, adds connections between endpoints of both features.
        If feature is a ladder, adds a connection between each point in the ladder and the other feature with the horizontal distance.
        Weights are added to limit jumps when possible.
        # TODO - See if custom behavior needed, for example for platforms where jumping down is only partially possible.
        """
        assert direction in ["left", "right"], "Invalid direction for jump connection."
        connection_type = (
            MinimapConnection.JUMP_LEFT
            if direction == "left"
            else MinimapConnection.JUMP_RIGHT
        )
        if feature.height == 0:
            feature_end = feature.left if direction == "left" else feature.right
            other_feature_end = (
                other_feature.right if direction == "left" else other_feature.left
            )
            grid.node(feature_end, feature.top).connect(
                grid.node(other_feature_end, other_feature.top),
                connection_type=connection_type,
            )
            grid.node(feature_end, feature.top).weight = abs(
                feature_end - other_feature_end
            )
        elif feature.width == 0:
            # Jumping out of a ladder
            other_feature_end = (
                feature.left - horizontal_distance
                if direction == "left"
                else feature.right + horizontal_distance
            )
            # Don't connect the first nodes as the character may not be able to actually jump down the ladder from there
            for node in range(feature.top + 2, feature.bottom):
                grid.node(feature.left, node).connect(
                    grid.node(other_feature_end, other_feature.top),
                    connection_type=connection_type,
                )
                # No need to add weight on ladders as its very easy to jump down from them
                # grid.node(feature.left, node).weight = (
                #     abs(feature.left - other_feature_end) + 1
                # )

    @staticmethod
    def _add_fall_connection(
        grid: MinimapGrid,
        direction: str,
        feature: MinimapFeature,
        other_feature: MinimapFeature,
        horizontal_distance: int = 5,
    ) -> None:
        """
        Adds connections between endpoints of the feature and points of the other feature a certain horizontal
        distance from those endpoints.
        """
        assert direction in ["left", "right"], "Invalid direction for fall connection."
        connection_type = (
            MinimapConnection.FALL_LEFT
            if direction == "left"
            else MinimapConnection.FALL_RIGHT
        )
        feature_end = feature.left if direction == "left" else feature.right
        other_feature_pt = (
            feature_end + horizontal_distance
            if direction == "right"
            else feature_end - horizontal_distance
        )
        grid.node(feature_end, feature.top).connect(
            grid.node(other_feature_pt, other_feature.top),
            connection_type=connection_type,
        )

    @staticmethod
    def _add_portal_connection(
        grid: MinimapGrid,
        source_nodes: list[tuple[int, int]],
        target_node: list[tuple[int, int]],
    ) -> None:
        """
        Adds connections between nodes into the grid based on portals in-game.
        Weight is left unchanged (No extra cost to use portals; in most cases its.
        """
        assert len(target_node) == 1, "Portal target must be a single node."
        target_node = target_node[0]
        for source in source_nodes:
            grid.node(*source).connect(
                grid.node(*target_node), connection_type=MinimapConnection.PORTAL
            )

    @staticmethod
    def _add_jump_into_ladder_connection(
        grid: MinimapGrid,
        direction: str,
        feature: MinimapFeature,
        other_feature: MinimapFeature,
        jump_horizontal_distance: int = 3,
        jump_vertical_distance: int = 4,
    ) -> None:
        """
        Adds connections between nodes into the grid based on jump into ladder in-game.
        # TODO - Change if custom nodes are needed here.
        """
        assert (
            feature.height == 0 and other_feature.width == 0
        ), "Invalid features for jump into ladder."
        assert direction in [
            "left",
            "right",
        ], "Invalid direction for jump into ladder."
        horizontal_distance = (
            -jump_horizontal_distance
            if direction == "right"
            else jump_horizontal_distance
        )
        connection_type = (
            MinimapConnection.JUMP_RIGHT_AND_UP
            if direction == "right"
            else MinimapConnection.JUMP_LEFT_AND_UP
        )

        grid.node(other_feature.left + horizontal_distance, feature.top).connect(
            grid.node(other_feature.left, feature.top - jump_vertical_distance),
            connection_type=connection_type,
        )
