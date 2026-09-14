"""
Standalone tool for defining minimap coordinates for a new or existing map.

Usage
-----
    python toolkit/create_map.py --map Line1Area1 --ign YourCharacterName

Run it while the game is open and your character is standing in the map you
want to record. Add `--scale 8` for small maps that are hard to click at the
default zoom.

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
Unlike the rest of configs/, `configs/maps/` IS tracked in git -- commit a new
map so everyone else can bot it too.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maple.model.mechanics import MapleMap


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Record or edit a map's minimap layout.",
        epilog="Saves to configs/maps/<map>.json. See docs/FIRST_BOT.md.",
    )
    parser.add_argument(
        "--map",
        required=True,
        dest="map_name",
        help="Map identifier, used as the JSON filename (e.g. Line1Area1).",
    )
    parser.add_argument(
        "--ign",
        required=True,
        help="Your in-game character name, used to find the client window.",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=5,
        help="Editor zoom in pixels per minimap cell. Raise it for small maps.",
    )
    args = parser.parse_args()

    MapleMap(
        args.map_name,
        open_minimap_editor=True,
        ign=args.ign,
        scale=args.scale,
        include_character_position=True,
    )


if __name__ == "__main__":
    main()
