from pathfinding.finder.a_star import AStarFinder

# Idea - use the GridNote connections for "teleporters" between points and "portals" between minimaps.
# Idea - use the GridNote connections for "holes" in the grid, for example gaps between platform and/or ladders.
class MinimapPathFinder(AStarFinder):
    """
    AStarFinder path finding algorithm with custom particularities for the minimap, which are:
    - Diagonal movement is not allowed.
    - The grid may contain "teleporter" between two points, for which "instant" travel is possible.
        The cost of travelling through a teleporter should be 0. (smallest weight?)
    - Horizontal paths ("platforms") can be jumped down from, provided there is a platform below. # TODO - Maybe this should be handled before grid creation?
        The cost of jumping down should be 0 (or very small, since it is nearly instantaneous).
    - The grid may also contain "portals" towards other grids, used to travel between minimaps.
    - There may be "holes" in the grid, for example gaps between platform and/or ladders.  # TODO - Maybe this should be handled before grid creation?
        These holes are traversable if they are small enough for the character to jump over, at no extra cost.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


