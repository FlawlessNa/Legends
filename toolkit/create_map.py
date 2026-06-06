"""
Standalone tool for defining minimap coordinates for a new or existing map.

Usage
-----
1. Set MAP_NAME to the map's identifier (used as the JSON filename).
2. Set IGN to your in-game character name so the editor can locate the client window.
3. Run this script while the game is open and your character is standing in the map.

The editor opens with three modes:

  Trail Recording   – Walk around the map while the tool records your path as
                      coloured dots (blue = platform, green = ladder, grey = airborne).
                      Click "Set Start Dot" then "Set End Dot" to select a segment,
                      choose Platform or Ladder, give it a name, and click
                      "Mark as Feature".  Repeat for every platform and ladder.

  Feature Selection – Draw bounding boxes directly on the canvas, or fine-tune
                      features created from the trail.  Also used to add portals
                      (links between two cells, one-way or bidirectional).

  Pathfinding       – Visualise and test the computed pathfinding graph once
                      features are defined (requires scale_x / scale_y in the JSON).

Click "Save Edits" in any mode to write the config to
  configs/maps/{MAP_NAME}.json

That file is everything MapleMap needs at runtime; no game XML files required.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maple.model.mechanics import MapleMap

# ── configure here ────────────────────────────────────────────────────────────
MAP_NAME: str = 'GhostShip1'
IGN: str = 'StarBase'
SCALE: int = 5   # editor zoom: pixels per minimap cell (increase for small maps)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    MapleMap(
        MAP_NAME,
        open_minimap_editor=True,
        ign=IGN,
        scale=SCALE,
        include_character_position=True,
    )
