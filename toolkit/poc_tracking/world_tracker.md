# World tracker (POC)

Reads the character's position in **virtual coordinates** (the map's own, the
"world" coordinates) from the play area, on any map and any client size, and
shows it on a render of the map. A proof of concept to compare with the other
two POCs; it is not wired into the bot.

**It never sends a key or a click to the game.** It only copies the client's
pixels (`botting.screen.frame_source`). The only keys it reads are the ones
pressed in its own window.

## Run it

From the repo root, with the Legends venv:

```
python toolkit/poc_tracking/world_tracker.py --map "Damp Forest"
python toolkit/poc_tracking/world_tracker.py --map 10002000 --log run.csv
```

- `--map` takes an id or a unique name, as `Catalogue.map` does
  (`"Victoria Road: Ellinia"` if a name is shared). Everything else comes from
  `game_data`: there is no map file.
- `--store PATH`: the `game_data` store, `data/game_data` by default. The main
  checkout's store is empty on this machine; the one used to build this is
  `Legends-worktrees/t311-minimap-frames/data/game_data` (extraction
  `3c238cfcb903ce34`).
- `--frames DIR` replays PNGs instead of capturing (`--delay` ms per frame,
  space pauses, `q`/Esc quits). With `--labels tests/frames/v2.json
  --no-window` it prints the offline evaluation below.
- `--log FILE` writes one CSV row per frame: status, method, confidence,
  camera, character and minimap positions, timings.
- `--no-minimap` turns the minimap read off.

Start-up renders the map's static layers once (0.2 s for Damp Forest, 1 to 3
s for Ellinia; cached in `data/poc_tracking/`), then the display render
(about 5 s for Ellinia). **Put the window beside the game, not over it**:
Desktop Duplication copies the screen, so a window over the client is
captured too. When the game isn't the foreground window, the capture is
marked "not trusted" in the panel, but still read.

## What it shows

One window: the whole map, downscaled, and a panel.

- **Green rectangle**: the camera (the view's top-left plus the play area's
  size), drawn only when registration is LOCKED.
- **Red dot and trail**: the character's feet, in virtual coordinates.
- **Cyan ring**: where the minimap marker says the character is (a simple
  read; the sibling minimap POC does it properly).
- Panel: the capture with every name tag found (the own one in red), the
  camera status (`LOCKED` or `UNSURE`, the method, the confidence and peak
  ratio), camera and character world x/y, the minimap's, the client size,
  milliseconds per step and fps. When registration is unsure, no position is
  shown: never a guess.

## How it works

1. **Camera, 1:1 clients (800x600 to 1366x768).** The map's static layers
   (tiles, objects, backgrounds fixed to the map; animated objects and
   scrolling backgrounds masked out) are drawn pixel-identically by the
   client. Exact-colour voting finds the camera, seeded by the last camera
   (±160 px), else over the whole map. Accepted only if, of 6,000 sampled
   pixels over the render's opaque pixels, at least 15% match exactly *and*
   the share is 1.5 times that at any of the 8 neighbouring cameras.
2. **Camera, upscaled clients (1920x1080).** The client draws the play area
   at 1366x768 and **upscales it bilinearly** (confirmed: the render upscaled
   bilinearly matches 94–97% of pixels within 12 levels at the right camera,
   nearest-neighbour only 67%). A coarse masked NCC at 1/8 proposes 6
   cameras, or the last camera is the one candidate; each is searched around
   and checked by that "near share" (≥ 0.3, and 1.2 times its neighbours).
3. **Character.** The production YOLO weights (`fetch_models.py global`)
   don't find the character on MSCW frames (1 detection in 5 frames tried), so
   the fallback is the **name tag**: white text on the plain tag's dark
   translucent box, 2 px under the feet (the box's top is found from its
   edge). The own tag is the one 40–170 px below the minimap's position and
   within 40 px of it in x; with no minimap, the one nearest the last
   position; else the one nearest the screen's centre column (marked unsure).
4. **Minimap.** `MinimapReader` (on `dev`) finds the frame and the marker in
   the map area; the marker is moved onto the map's own minimap canvas (the
   area centres a narrow canvas and scrolls a tall one), then
   `canvas * 2**mag - centre`.

## Offline results (frame set v2)

`--frames .../data/frames/v2 --labels .../tests/frames/v2.json`, both maps.
Each map's run also registers the other map's frames, as a wrong-map test.

| | Damp Forest | Ellinia |
| --- | --- | --- |
| Camera, unseeded, 1:1 sizes | 59/60 (miss: f043, mid-resize, labelled unsure) | 37/37 |
| Camera, unseeded, 1920x1080 | 3/6 (f059 mid-resize; f063–f064 behind the Options dialog) | 8/8 |
| Same, in the tracking run (seeded by the previous frame) | f063–f064 locked | all |
| Wrong-map frames accepted | 0/45 | 0/66 |
| Seeded result = unseeded result | 62/62 | 45/45 |
| Registration time, 1:1, unseeded / seeded (median) | 2–3 ms / 2–3 ms | 3 ms / 3 ms |
| Registration time, 1920x1080, unseeded / seeded | 110 ms / 31 ms | 196 ms / 52 ms |
| Whole step (registration + minimap + tags), tracking run | 9–12 ms at 1:1, 50 ms at 1920 | 9–13 ms, 66 ms |
| Character found (frames of this map) | 46/66 | 41/45 |
| Character − minimap label, x | median 6, max 35 | median 0, max 2 |
| Character − minimap label, y | +103 (+102..+106) | +97 (+97..+98) |

- **The minimap reads about 100 px above the feet**, consistently (the
  research note's finding, now on 84 frames). The x error of up to 35 px on
  Damp Forest is on stills where the character was moving.
- **Consistent across client sizes.** The same spot at 800x600, 1024x768,
  1366x768 and 1920x1080, each with its own camera, gives the same character
  position to 1 px: (468, −1282) on Damp Forest, (−334, −946) on Ellinia.
  On Damp Forest that y is a foothold's (−1395 on f010 is foothold 42's
  exactly).
- **Character misses are honest**: the character or its tag behind a window
  (f016–f019, f045–f052, f057–f058), cut by a sword (f025), or the mouse
  cursor on the tag (j_1024 pageup). No wrong tag was picked when the
  minimap was read.

## Limits

- **Name tags only.** A hidden tag (some players turn it off), one under a
  window, or the cursor on it means no position. Styled tags
  (`UI/NameTag.img`) and very dark scenes are untested. Without the minimap,
  the pick between several players is a guess (it says so).
- **Feet when airborne** are where the tag is, which follows the character;
  not snapped to a foothold.
- **Upscaled clients are slow to re-acquire** (110–200 ms) and fail globally
  when a big dialog covers the static layers; the seed carries the lock
  through. Only 1920x1080 is known to be upscaled; other sizes above
  1366x768 are assumed to scale the same way.
- **Maps with little static art in view**, repeated identical tiles, or
  map-wide effects lower the share; the gate then says UNSURE rather than
  drifting. Not tested beyond two maps.
- **Map changes** aren't detected: on another map it reads UNSURE until
  restarted with the new `--map`.

## Not verified

- **Nothing here ran against the live game.** Capture, live fps, the
  viewer's own cost, and the effect of the capture not being trusted are
  untested. The offline step is 9–13 ms at 1:1 (60 fps would leave room);
  the drawing and the capture add to that.
- Camera tracking between consecutive live frames (v2 is stills seconds
  apart): the 1:1 seed reaches ±160 px; the 1920x1080 seed only ±12 px,
  beyond which the 110–200 ms global search runs.
- The tag-to-feet offset (2 px) is checked on footholds at 1:1 only.
- Animated backgrounds, front backgrounds, dark or tinted maps, towns with
  many players.
