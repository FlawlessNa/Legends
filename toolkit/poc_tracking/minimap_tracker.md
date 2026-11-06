# POC: minimap tracking

`minimap_tracker.py` reads the character's position from the minimap and places
it on the map's whole `miniMap/canvas`, on any map. It is one of three POCs to
compare; the other two track world coordinates from the play area.

**Capture only.** It copies the client's pixels with Desktop Duplication and
draws in its own window. It never sends a key or a click to the game.

## Run it

From the repo root, with the venv's Python, and the game data extracted
(`python -m game_data extract`; see `docs/agents/game-data.md`):

```
python toolkit/poc_tracking/minimap_tracker.py --map Henesys
python toolkit/poc_tracking/minimap_tracker.py --map 10002000
python toolkit/poc_tracking/minimap_tracker.py --map "Dungeon: Damp Forest" --log out.csv
python toolkit/poc_tracking/minimap_tracker.py --map auto
```

- `--map`: a map name (as `game_data show map` takes it), an ID, or `auto` to
  identify the map from the minimap. `auto` identifies again by itself when the
  map changes (at most every 2 s while it can't tell).
- `--frames DIR`: replay saved PNGs instead of capturing.
- `--labels FILE --headless` (with `--frames`): print the accuracy against a
  frame set's labels, and open no window.
- `--log FILE`: a CSV of time, frame, status, canvas x/y, world x/y,
  confidence and map ID, one row per frame.
- `--store PATH`: the game data store. By default `data/game_data` in this
  checkout, else the main checkout's, else the one in the
  `t311-minimap-frames` worktree.
- `--fps N`: cap the capture rate.

Keys: `q` or Esc quits, `c` clears the trail, `r` identifies the map again
(with `auto`). With `--frames`: space plays or pauses, `n` and `p` step.

Keep the minimap **expanded** (with or without the banner). The game must be
on the primary monitor, as for the bot.

## What it shows

- Left: the minimap as captured, frame included, scaled up.
- Right: the map's whole canvas, scaled up (4x when it fits), with a dark
  margin around it. The yellow rectangle is the map area, where the minimap
  window is on the canvas. The red dot is the character; the cyan line is its
  trail. When the position is unsure, the last known one is a hollow grey
  circle.
- Status lines: `READ`, `COVERED`, `UNSURE` or `ABSENT` with the reason; the
  map; the position in canvas pixels and in world pixels; the confidence (the
  share of the canvas's visible opaque pixels drawn exactly, how many there
  are, how close the runner-up placement scored, or `tracked` when the
  placement was kept from the last frame); the frame look, area size and
  canvas size; fps and the tracker's own time per frame.

## How it works

1. The minimap frame is found by its sprites, `UI/MiniMap.img/MaxMap` or
   `MinMap`: `nw` (checked with its `n` and `w` neighbours), then `ne` along its
   row, `sw` along its column, and `se` where both put it. The map area is the
   inside. Its size is read every time; nothing assumes 112, or any size.
   Where the frame was is checked first.
2. The map area is a window on the canvas, drawn 1:1. Along an axis the canvas
   fits in, it can sit anywhere inside the area; along one it doesn't, the area
   can show any part of it. Every such placement is scored by how many of a
   sample of the canvas's opaque (alpha 255) pixels are drawn exactly there.
   The best one is kept when at least 60% of the visible opaque pixels are
   drawn exactly (markers cover the rest), at least 80 are in view, and no
   placement 3 px away or more scores 90% as well (a canvas that repeats
   itself). The next frame searches near that placement first (±4 px across,
   ±8 px down), then everywhere. Both axes scroll the same way, so a wide town
   that scrolls sideways is handled like a tall one.
3. The character's marker, `Map/MapHelper.img/minimap/user`, is matched in the
   area (with a margin), and its origin gives the position on the canvas.
   World pixels are `canvas * 2**mag - center`, from the catalogue's
   `Minimap`.
4. `--map auto` scores every canvas in the catalogue (301 on build
   3c238cfcb903ce34) with a small sample, then checks the best five fully.

## Offline results (frame set v2)

111 frames of Damp Forest (92x158 canvas in a 130x112 area, centred and
scrolling) and Ellinia (171x318 in 171x112), at 800x600, 1024x768, 1280x720,
1366x768 and 1920x1080. Labels from `tests/frames/v2.json` on the
`t311-minimap-frames` worktree:

| Run                         | Positions exact | Wrong | Unsure | No-position frames read anyway |
| --------------------------- | --------------- | ----- | ------ | ------------------------------ |
| `--map auto`, in order      | 105 / 105       | 0     | 0      | 1 of 6 (f002)                  |
| `--map auto`, each cold     | 105 / 105       | 0     | 0      | 1 of 6 (f002)                  |
| `--map "Dungeon: Damp Forest"` | 62 / 62 Damp  | 0     | 43 (all Ellinia) | 1 of 6 (f002)        |
| `--map Ellinia`             | 43 / 43 Ellinia | 0     | 62 (all Damp)    | 0 of 6               |

Given the wrong map, every frame reads unsure: no number is made up. f002 is
labelled unsure because it isn't the client (the desktop was over a black
screen), but its minimap pixels are the client's, so this POC reads them: it
has no frame-usable check (see below).

Synthetic frames (a `MaxMap` or `MinMap` frame drawn around areas of 96x80,
130x112, 171x112 and 220x150, on Henesys, Ellinia, the largest canvas
(431x428) and 28 random maps, scrolled to a random offset): 124 of 124
exact.

Time per frame, in order: median 3 ms. A search from nothing (first frame, or
the minimap moved) costs 150 to 300 ms, mostly finding the frame over the
whole client; identifying the map with `auto` costs about 0.7 s. The replay
loop, drawing included, ran at about 46 fps on 1366x768 frames.

## Known limits

- **No frame-usable check.** A frame copied while another window is in front
  is still read: the canvas check rejects pixels that aren't the minimap, but
  a stale minimap left on screen reads as if live. The status line shows the
  capture's reason in yellow.
- **The marker at the area's edge** can be clipped, and then reads `COVERED`.
  So can a marker under another marker or the mouse cursor.
- **Minimised** reads `UNSURE`; a minimap partly off the client, or covered by
  another window, reads `ABSENT`.
- **A canvas that repeats itself** reads `UNSURE` (ambiguous) until a
  placement is found that stands out; once found, it is tracked near the last
  one without re-checking the runner-up.
- **`auto` picks the best of 301 canvases.** Two maps sharing one canvas would
  be told apart by nothing; the first is kept.
- The search grows with how far the canvas scrolls: the largest canvas in a
  small area takes about 0.3 s to place from nothing.

## Not verified

- **Never run against the live game.** Desktop Duplication, `find_client` and
  the live frame rate are untested here; only replayed PNGs and synthetic
  frames were.
- **Only two real maps.** Henesys, which may scroll sideways, and any map
  other than Damp Forest and Ellinia, were tested only on synthetic frames
  built from the game data. Whether the client centres, scrolls or clamps the
  view the way this assumes on every map is not seen.
- That the area's background behind transparent canvas pixels never matches
  the canvas by chance is assumed (only alpha 255 pixels are compared).
- World pixels follow the catalogue's `Minimap` transform; they were not
  compared with positions read from the game.
