import numpy as np
from pathfinding.core.grid import Grid

from botting.utilities import Box
from royals.interface import Minimap


def generate_grid_template(handle: int,
                           minimap: Minimap,
                           horizontal_tolerance: int | None = None) -> Grid:
    """
    Generates a "grid"-like array of the minimap, which includes royals mechanics.
    Those mechanics are:
        - Connect nodes between parallel, horizontal platforms, provided they are not too distant (jump down).
        - Connect nodes between teleporters (can be one-way or two-way).
        - Connect nodes between portals (can be one-way or two-way) # TODO
    :param handle: Handle to the game window.
    :param minimap: Minimap instance that defines its height limit (in pixels), its teleporters and portals.
    :param horizontal_tolerance: Distance, in pixels, to tolerate between two platforms for jumps.
    :return: Grid object
    """
    if horizontal_tolerance is None:
        horizontal_tolerance = minimap.horizontal_jump_distance
    map_area = minimap.get_map_area_box(handle)
    canvas = np.zeros((map_area.height, map_area.width), dtype=np.uint8)
    canvas = minimap.preprocess_for_grid(canvas)

    base_grid = Grid(matrix=canvas)
    add_portals_connections(base_grid, minimap)
    add_jump_down_connections(base_grid, tolerance=minimap.height_limit_for_jump_down, canvas=canvas)
    add_jumpable_connections(base_grid, tolerance=horizontal_tolerance, canvas=canvas)
    return base_grid


def add_portals_connections(base_grid: Grid, minimap: Minimap) -> None:
    """
    Adds connections between nodes into the grid.
    :param base_grid: Base grid to add connections to.
    :param minimap: Minimap instance that defines its height limit (in pixels), its teleporters and portals.
    :return: Grid with added connections.
    """
    for pairs in minimap.teleporters:
        from_box, towards_box = pairs
        _add_connection_from_boxes(base_grid, from_box, towards_box)


def add_jump_down_connections(grid: Grid,
                              tolerance: int | None,
                              canvas: np.ndarray) -> None:
    """
    For each horizontal platform, looks into whether there is a platform below it.
    If so, adds connections between them, provided the distance between them tolerated.
    :param grid: Grid to add connections to
    :param tolerance: Distance, in pixels, to tolerate between two platforms.
    :param canvas: Modified image representing the grid. Easier to work with.
    :return:
    """
    if tolerance is None:
        tolerance = grid.height
    for row_idx, col_idx in zip(*np.where(canvas > 0)):
        # Look into there is a walkable cell below the current one
        targets = canvas[row_idx+1:, col_idx].nonzero()[0]
        if len(targets) == 0:
            continue
        first_below = row_idx + 1 + targets.min()
        if first_below - row_idx > tolerance:
            continue
        grid.node(col_idx, row_idx).connect(grid.node(col_idx, first_below))


def add_jumpable_connections(grid: Grid,
                             tolerance: int,
                             canvas: np.ndarray) -> None:
    for row_idx, col_idx in zip(*np.where(canvas > 0)):
        # If either left or right of current cell is not walkable, look into whether
        # There is a walkable cell within tolerance distance
        if canvas[row_idx, col_idx-1] == 0:
            left_targets = canvas[row_idx, col_idx-tolerance-1:col_idx].nonzero()[0]
            if len(left_targets) > 0:
                closest_left = col_idx - tolerance - 1 + left_targets.max()
                grid.node(col_idx, row_idx).connect(grid.node(closest_left, row_idx))

        if canvas[row_idx, col_idx+1] == 0:
            right_targets = canvas[row_idx, col_idx+1:col_idx+tolerance+2].nonzero()[0]
            if len(right_targets) > 0:
                closest_right = col_idx + 1 + right_targets.min()
                grid.node(col_idx, row_idx).connect(grid.node(closest_right, row_idx))


def _add_connection_from_boxes(grid: Grid,
                               from_box: Box,
                               towards_box: Box) -> None:
    """
    Adds connections between two boxes in the grid.
    Include each cell in the boxes.
    :param grid: grid to add connections to.
    :param from_box: Box to connect from.
    :param towards_box: Box to connect towards.
    :return: Grid with added connections.
    """
    for x in range(from_box.left, from_box.right+1):
        for y in range(from_box.top, from_box.bottom+1):
            node = grid.node(x, y)
            for x2 in range(towards_box.left, towards_box.right+1):
                for y2 in range(towards_box.top, towards_box.bottom+1):
                    node.connect(grid.node(x2, y2))
