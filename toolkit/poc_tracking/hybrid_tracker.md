# Hybrid tracker (proof of concept)

Reads the character's position two ways at once, and shows them side by side
on the map's full render:

- from the **minimap** (the `user` marker on the map's `miniMap/canvas`), and
- from the **play area**, in virtual coordinates: the camera registered against
  `game_data`'s static render, plus the character's feet on screen.

A third, **fused** answer says whether the two agree. The script **only
captures**. It never sends a key, a click or any other input to the game.

## Run it

```
# live: the game must be running and on the primary monitor
.venv\Scripts\python.exe toolkit\poc_tracking\hybrid_tracker.py --map "Ellinia" ^
    --store C:\Users\nassi\Games\Botting\Legends-worktrees\t311-minimap-frames\data\game_data ^
    --log hybrid.csv

# replay saved frames (PNG, as captured)
.venv\Scripts\python.exe toolkit\poc_tracking\hybrid_tracker.py --map 10005031 ^
    --store <store> --frames <dir> --glob "f0*.png" [--headless]
```

- `--map`: an ID, or a name `game_data` resolves to one map (`Henesys`,
  `"Victoria Road: Ellinia"`). Everything else comes from the store: the
  render, the minimap canvas and its transform, the frame sprites, footholds.
  There is no hand-made map file.
- `--store`: the `game_data` store. The default is this checkout's
  `data/game_data`, which is empty on this machine, so pass the t311 one.
- `--weights`: YOLO weights. By default, `data/models/production/global/...`.
  When they're absent, which is the case on this machine, the name-tag finder
  is used instead (see below). The console says which one is used.
- `--log out.csv`: one row per frame, with all three estimates, each source's
  status and confidence, the camera, and the timings.
- `--headless`: no window. Prints a line per frame and a summary. Without it,
  the summary is printed when the window closes.
- The first run on a map renders it and caches the renders under
  `data/poc_tracking/<build>/`: 0.3 s for Damp Forest, about 5 s for Henesys or
  Ellinia.

Keys, in the tracker's own window: `q` or Esc quits, space pauses, `c` clears
the trails and the learned name tag.

## What the window shows

- **Left:** the map's full render, scaled to fit. The grey rectangle is the
  registered camera, with a trail for each source:
  - **light blue ring**: the minimap marker, converted as #365 does
    (`c * 16 - centre`). A line runs from it to a dot, the feet it implies
    (see "the 6 px offset").
  - **green cross**: the world estimate.
  - **magenta square**: the fused estimate. There is none while the sources
    disagree or neither reads.
- **Top right:** the captured frame, with the minimap's map area (blue) and the
  name tag that was found (green).
- **Middle right:** the render at 1:1 around the estimate, with the footholds in
  white. At this scale one minimap pixel is 16 px, so the difference between
  the sources can be seen.
- **Bottom right:** each source's value or `UNSURE` and why, its confidence
  (the share of the canvas drawn; the camera's exact share or NCC score; the
  name tag's darkness or learned-match score), the fused status (`agree`,
  `DISAGREE`, `minimap only`, `world only`, `unsure`), the raw difference in
  virtual px, the residual in canvas px, ms per source, and fps.

## How each source reads

**Minimap.** The frame's `nw`, `n` and `se` pieces (`MaxMap` or `MinMap`) give
the map area, whatever its size. The canvas is placed in it by exact colour
over every placement the area allows: centred or scrolling, on either axis. The
`user` marker is matched in the area, and its origin, less the canvas offset,
is the canvas pixel. It reads `UNSURE` when the canvas isn't found (another
map, minimised, closed) or the marker isn't found.

**World.**
- **Camera, 1:1 clients:** exact-colour voting against the static render
  (tiles, objects, backgrounds with `rx = ry = -100`). It is seeded by the last
  camera (±200 px), else voted over the whole map. A peak counts when it has 5
  or more votes and an exact share of at least 0.2. A peak that would put the
  minimap's position off screen is rejected: the minimap cross-checks the
  camera.
- **Camera, clients wider than 1366:** the frame is downscaled to 1366 wide.
  Masked normalised correlation, coarse to fine, is then run on a 3x3 grid of
  tiles, keeping the best half, so a window covering part of the view doesn't
  sink it. It is seeded by the last camera, or by the minimap, clamped to the
  map.
- **Feet:** YOLO's `Character` box when weights exist (untested). Otherwise
  the **name tag**: white text on the translucent dark box drawn under the
  feet. Once the same tag width has been seen three times where the minimap
  puts the character, that tag's text is learned and matched from then on. So
  another player's or a mob's tag drawn against it can't pull the read
  sideways. A tag of another width is then `UNSURE`, never a guess.
  Feet = tag text top − 5 px, calibrated against footholds (below).

**Fusion.** The world position predicts the marker's canvas pixel:
`(floor((x+cx)/16), floor((y+cy)/16) − 6)`. Within one pixel on each axis,
the sources agree, and the world position is kept as the finer of the two.
Otherwise they disagree, and there is no fused position.

## Offline results (frame set v2, store 3c238cfcb903ce34)

| | Damp Forest (66 frames, 800x600–1920x1080) | Ellinia (43 frames, 800x600–1920x1080) |
| --- | --- | --- |
| Minimap read | 63/66. The 3 misses are a minimised or closed minimap: correctly `UNSURE`. The 62 labelled ones equal `v2.json` exactly. | 43/43 |
| Camera found | 63/66 (f042 is dimmed; on f043 and f059 the minimap is closed and the view is covered) | 43/43 |
| World read | 49/66. The 14 misses with a camera have the tag covered by a window (800x600 skill window, game menu), another player standing on it, or the character off screen. All are `UNSURE`. | 43/43 |
| Fused | agree 48, minimap only 15, world only 1, unsure 2, **DISAGREE 0** | agree 43 |
| Minimap − world, p10/median/p90 | dx −14/−7/−2, dy −104/−103/−102 | dx 0/0/0, dy −98/−97/−97 |
| Marker vs predicted canvas pixel | y: 0 on 48/48; x: ±1 on 5/48 | 0 on 43/43 |
| ms per frame, median (p90) | minimap 2.7 (214), world 4.4 (9) | minimap 3.3 (179), world 6.7 (54) |

- **Speed.** At 1:1, the median is about 7 to 10 ms per frame for both
  sources. A scaled 1920x1080 frame takes 37 to 80 ms (the NCC). The minimap's
  p90 is its whole-frame search (120 to 470 ms), which runs on the first frame
  and when the client size or the minimap changes. Live, after a failed search,
  it waits 0.5 s before searching again. Compute alone would allow about 100
  fps at 1:1 and 15 to 25 fps at 1920x1080. The live rate, with capture and
  the window, has not been measured.
- **Disagreements seen.** Before the learned tag, f018, f022 and f031 read the
  wrong tag: another player's, or ours merged with "Snail". Fusion flagged all
  three as DISAGREE (residuals of 2 to 4 canvas px). With the learned tag, f022
  and f031 read right, and f018 says `UNSURE`.

## The ~6 px y offset: what the side-by-side shows

- **It is exactly 6 canvas rows, not about 100 virtual px.** On every frame
  where both sources read (91 frames, two maps, all five client sizes), the
  marker's canvas row is `floor((feet_y + cy) / 16) − 6`. The world feet sit
  on the foothold to 0 to 2 px. The virtual difference therefore varies, from
  −97 (Ellinia, feet 1 px into their canvas pixel) to −102 or −103 (Damp
  Forest, feet 6 to 7 px in). This is the rounding of the feet to their pixel,
  plus 96.
- **x has no offset.** The marker's column is `floor((x + cx) / 16)`, ±1 on
  5 of 91 frames. Those are walking frames, plausibly sampled a tick apart.
- **It isn't the labels.** The reader reproduces `v2.json` on all 62 Damp
  Forest frames, and the y offset holds on Ellinia frames too.
- **Likely cause (unverified):** the client draws the 12x12 `user` marker with
  its bottom centre on the character, instead of its WZ origin `(6, 6)`. Its
  centre then lands 6 px up. The alternative, a fixed 96 virtual px, can't be
  told apart while every map has mag 4.
- **For #365:** the feet are at canvas
  `(marker_x, marker_y + 6)`. The marker read as virtual (`c*16 − centre`) is
  8 px left of and 104 px above the feet, on average.

## Limits

- The name tag is a stand-in for YOLO. It needs the tag visible: a window over
  it, another player standing on it, or hidden names make the world source
  `UNSURE`. The first tag is learned where the minimap puts the character. If
  another player's tag of a steady width stood there three frames running, it
  would be learned instead (`c` resets it).
- The rule "wider than 1366 means upscaled from 1366" was measured at
  1920x1080 only.
- The camera needs static art in view. Maps of repeated identical tiles, dark
  or tinted maps, and maps whose fixed layer covers little of the view are
  untested.
- The minimap needs the expanded frame. Minimised or closed, it is `UNSURE`.
- Live capture uses Desktop Duplication of the primary monitor, so the
  tracker's window must not cover the game. Frames are processed even while the
  game isn't in front, and the frame name says so.

## Unverified (no live game was run)

- **The live path as a whole.** `find_client`, `frame_source().grab`, the fps,
  the window on a real desktop, and whether capture stays lossless (it must be,
  for exact colours).
- **The YOLO path.** There are no weights on this machine, so the code that
  picks the `Character` box nearest the minimap's prior never ran.
- **Henesys and other big towns.** Henesys loads (render 6896x1189, 5 s
  first time), and on an Ellinia frame it correctly reads `UNSURE` from both
  sources. Whether its 431-px-wide canvas scrolls horizontally in the map area,
  and is placed right there, has no frame to check against.
- **Animated objects** (drawn at frame 0) and **map effects** (the dimming on
  f016 to f019 and f042) cost votes. f042 lost its camera to it.
- **Scaled clients' tag thresholds** (white ≥ 190, dark ≤ 110) were set on two
  1920x1080 frames.
