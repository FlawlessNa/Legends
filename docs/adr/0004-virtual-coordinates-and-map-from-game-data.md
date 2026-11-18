---
status: accepted
---

# Navigation works in virtual coordinates, on a map read from the game files

## Context

Until epic #302 (Part 2), the map was a hand-made JSON file per map under
`configs/maps/`, drawn at minimap scale in a GUI editor. `MapleMinimap` built
`MinimapGrid` from it, one node per minimap pixel, and `MinimapPhysics` scaled
the client's physics down to that grid with each file's `scale_x`/`scale_y`.
The position fed in was the minimap marker's pixel.

On MSCW that chain broke in three places:

- The minimap's map area is a window that scrolls on tall and wide maps, so a
  marker pixel isn't a fixed place.
- None of the files described an MSCW map, and each new map needed a person
  at the client to draw it.
- A minimap pixel is 16 virtual px (every MSCW minimap is `mag` 4). Rope
  grabs, narrow landings and edge stops need more precision than that.

The client's own files hold every map's footholds, ropes, ladders, portals
and minimap transform, in the map's own unit (`CONTEXT.md`, Virtual
coordinates). `game_data` extracts them, and the play area can be read to the
pixel against the map's static render.

## Decision

- **Virtual coordinates are the navigation unit.** Positions
  (`Reading[VirtualPosition]`), Platforms, the Foothold graph, Paths and
  Movement Plan lengths are in virtual px, and the physics are virtual px/s
  (`VRPhysics`). Telemetry keeps its canvas-px fields beside the new
  virtual ones (additive, ADR 0001).
- **The map comes from `game_data`.** `WorldMap` is built from the
  extraction's `MapData` for the map the profile names (`settings.map`: a game
  name, an id, or `auto`). Paths are planned on its `FootholdGraph`. Nothing
  reads a hand-made map file. `game_data` still imports neither `maple` nor
  `botting`.
- **Both position reads are kept and fused.** The play area gives precision
  and the minimap is the check and the fallback. A position that can't be
  placed is `UNSURE`, never a plausible number.
- **Retired** (#399): `configs/maps/` (but see Consequences),
  `MapleMinimap`, `MapleMap`, `MinimapEditsManager`, `MinimapGrid`,
  `MinimapPhysics`, the GUI map editor (`maple/model/mechanics/minimap_creation/`),
  `toolkit/create_map.py` and the profile's `game_map`. A profile that still
  sets `game_map` refuses to start, naming `map`, and saying the mobs now
  come from the map.

Rejected:

- Minimap pixels. They round away the play area's precision and need
  footholds shrunk 16×.
- A 1-px grid in virtual px. The #302 benchmark put it about 256× slower to
  build, at 1.6 to 5 GB.
- A coarse grid rasterised from `game_data`. It is fast, but not exact, and
  would be replaced anyway.
- Keeping the map files beside the game data. Two sources of map facts
  disagree silently, and the files can't describe MSCW maps.

## Consequences

- Starting a bot needs no hand-made map file, only a map the extraction's
  Catalogue knows. A Build without an extraction can't start a bot that names
  a map.
- The mobs a bot's detection looks for came from the map file's `mobs` list.
  They moved to the profile's `mobs` setting for a while, not derived from
  the map's spawns, since that would change which detection classes run and
  was a separate decision. **Amended by #548 (the maintainer's decision,
  2026-11-15):** that decision is taken. The profile names only its `map`,
  and the mobs are the map's mob spawns in `game_data` (`WorldMap.mobs`),
  hidden spawns aside, each by its detection class: its name in the client's
  strings without spaces and dots, as `synth` names a model's classes
  (`game_data.scenes.class_name`, used by `maple/bots/map_mobs.py`). A
  profile that still sets `mobs` refuses to start. A bot that detects mobs
  refuses to start when a mob the map has is detected by no model in its
  `models_path` (`models.manifest.json`'s `classes`, or a model's
  `recipe.json`): a named map's when the bot is built, `map: auto`'s once the
  map is identified. A map with no mobs starts, and a bot that detects none
  (the calibration bot) isn't checked. A bot now looks for every mob its map
  has, not a subset the profile listed.
- The one shipped map file was deleted by #546, with its directory. A
  profile that still sets `game_map` refuses to start.
- Custom rotation patterns (the map files' feature cycles) are gone. Rotation
  draws its targets on Platforms. A later epic may bring an editor back on top
  of `WorldMap`.
- Physics values, the Foothold graph's feasibility constants and Calibration
  constants are measured by Trials on a real map (`configs/trials/`), in
  virtual px.
- `maple/decision_makers/inventory_manager.py` is parked (`maple/AGENTS.md`).
  It still names the retired map-file attributes (`current_map`,
  `current_minimap`, the grid). It already fails at import, and reconnecting
  it means porting those to `WorldMap`.
