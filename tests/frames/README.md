# The frame sets

Each `<tag>.json` here holds what the real MSCW frames of release `<tag>` of
the private `legends-frames` repository should read as. The frames are never
committed (they show other players' names): `python scripts/fetch_frames.py`
downloads the tag in `CURRENT`. `docs/agents/testing.md` ("The frame set") has
the file format and how tests use it.

| Tag | Frames | What it adds |
| --- | --- | --- |
| `v1` | 66 | Damp Forest at 1366x768, 800x600, 1024x768 and 1920x1080 |
| `v2` | 111 | `v1` unchanged, plus Ellinia at every client size (quick slots, buffs, the stat window) |
| `v3` | 307 | `v2` unchanged, plus 196 frames of Henesys, Henesys Market, crowded Henesys and Ellinia climbing |

`v2` and `v3` carry three more readings on every frame: `camera`, `feet` and
`map_id`. `v2.json`'s other readings are as they were; `v3.json` repeats
`v2.json`'s 111 entries word for word.

## The position readings

All three are in **virtual px** (`CONTEXT.md`), the unit the map's footholds
and ropes are stored in.

- **`camera`**: `{x, y}`, the virtual coordinate of the play area's top-left
  pixel.
- **`feet`**: `{x, y}`, our character's feet. `covered` where the character is
  on screen but its name tag can't be read (under a window, behind an object
  drawn in front, under another player's chat balloon); the frame's `notes`
  says which.
- **`map_id`**: the map's ID in `game_data`'s catalogue (Damp Forest
  10005031, Ellinia 10002000, Henesys 10001000, Henesys Market 10001040).

All three are `unsure` on the three frames that aren't a trustworthy picture
of the client: `f002` (the desktop over the client), `f043` and `f059`
(mid-resize). Every other frame shows its map, so `camera` and `map_id` are
`read` there, a minimised or covered minimap included.

**The play area's size.** The client draws the play area at 1:1 up to
1366x768. Above that it draws it 768 high and upscales it: at 1366x768 for
1920x1080 and 2560x1440, and at **1228x768 for 1920x1200**. A position on
screen is divided by `client size / play area size` on each axis before the
camera is added. At 2560x1440 the whole client is upscaled, UI included, so
the minimap reads `unsure` there (as on `f043` and `f059`). The sizes were
measured on these frames, as the camera reads best (see
`toolkit/poc_tracking/label_frames.py`, `PLAY_AREA`); they are not read from
the client. The readers take them from `maple.screen.position.PLAY_AREAS`, and
read no other size above 1366x768.

## How they were made

Labelled offline, once, by running the POC trackers
(`toolkit/poc_tracking/`, PR #366) through
`toolkit/poc_tracking/label_frames.py`, then checked by eye on overlays and
corrected by hand where said below. No test runs the POCs: tests read these
files.

```
python toolkit/poc_tracking/label_frames.py --map 10001000 --frames DIR \
    --glob "henesys_1366x768_*.png" --out henesys_1366.csv \
    --tag DIR/henesys_1366x768_00.png:624,583,686,596 \
    --tag DIR/henesysmarket_1920x1080_010.png:1064,661,1148,678 \
    --tag DIR/henesys_1920x1200_00.png:868,911,965,931
```

One run per map and sequence, frames in name order (`v2` was run once per
map over all its frames).

- **`camera`**: `world_tracker`'s registration (exact-colour voting at 1:1;
  a coarse NCC proposal checked by the share of pixels within 12 levels of the
  static render upscaled bilinearly, above it), seeded by the previous frame.
  `hybrid_tracker`'s camera was read beside it as the second read. At 1:1 the
  two agree on every frame. Above 1366x768 they differ by more than 2 px on
  103 frames: the hybrid's NCC, seeded by its own last camera, drifts onto the
  wrong place, and it takes the play area as 1366 wide at 1920x1200. The
  world tracker's camera is the one the eye check confirmed on every frame,
  so it is the label.
- **`feet`**: our character's own name tag, found as a template cut from one
  frame per play-area scale (the `--tag` boxes above), over the whole frame
  above the status bar. No other character carries that text, so the tag
  can't be confused with another player's. Feet are the tag's centre column
  and `hybrid_tracker.TAG_TO_FEET` (5) play-area px above the tag's top, then:
  - **x** is rounded from the tag's centre plus 0.5 px. Fitted on these
    frames: on every rope frame (Ellinia, Damp Forest) and at Henesys's wall
    at x 3638, the tag's centre reads 0.2 to 0.6 px left of the rope's or the
    wall's x, which is where the character's x is.
  - **y**, at upscaled sizes only, is the map's foothold under the feet when
    the tag puts the feet within 1.5 px of it (the tag's row is 0.7 virtual
    px at 1920x1080), rounded; otherwise the tag's y, rounded. At 1:1 the
    tag's y lands on the foothold to the pixel wherever the character stands.
  - Airborne frames (jumps) are labelled where the tag puts the feet, which
    follows the character; nothing is snapped there.
- **`map_id`**: the map each run was given; for `v2`, the map its `minimap`
  reading names (`f037`, minimised, and the two stat-window frames by their
  camera matching only that map's render).
- **`minimap`** (`v3`'s new frames only, the existing reading's format):
  `hybrid_tracker`'s canvas pixel for the marker, which the production
  `MinimapReader` given the map's ID reads identically on every new frame.
  `self_position` is `null` where the marker is clipped at the canvas's edge
  (our character at Henesys's right end), which the reader reads as no
  position.
- **`chat`** (`v3`'s new frames only, `v1`'s format, #483): the production
  `ChatReader`'s kinds, each frame read with nothing remembered. Every
  distinct log (101 of them, frames whose rows' text pixels are the same
  taken once) was looked at with each row's kind written beside it, and every
  kind is the row's: a band is a megaphone (yellow, pink, teal, light blue,
  and the red band of a crate's announcement), yellow text and an event's
  light-blue text with no band are system, and white text with no band is
  general. No window or notice is over the log on any of them. The 11 frames
  at 2560x1440 are `unsure`: the UI is upscaled there, as for `minimap`.

### Corrected by hand

Each of these was looked at on a full-resolution crop with the template's
match box drawn.

- **A tag matched below the 0.8 threshold, accepted** (the box sits on our
  tag; the tag is partly behind a vine, a sign, a rope or another player's
  tag): `f007`, `f022`, `f025`, `f028`, `henesys_1920x1080_09`,
  `henesysL_1920x1080_07`, `henesysmarket_1920x1080_002`, `_028`, `_048`,
  `_052`, `henesyscrowd_1920x1080_012`, `_016`, `_028`, `_034`,
  `ellinia_1920x1080_028`, `_034`, `_044`.
- **A tag cut by the client's right edge, placed by its visible left part**
  (the template's left 55%): `henesys_1024x768_08` to `_10`,
  `henesys_1280x720_05` to `_10`, `henesys_1366x768_05` to `_10`,
  `henesys_1920x1080_10` to `_12`, `henesys_1920x1200_05` to `_10`, all of
  `henesys_2560x1440_*`, and `henesysL_1920x1080_00`. Every one gives
  (6308, 454), at every client size: the character standing at Henesys's
  right end.
- **A tag half under a window, placed the same way**: `f040` and `f048`,
  which give (468, -1282), as their neighbours on the same rope do.
- **`feet` `covered`**: `f016` to `f019`, `f045` to `f047`, `f050` to
  `f052`, `f057`, `f058` (windows), `henesys_1024x768_07`,
  `henesys_1280x720_03`, `henesys_1366x768_03` (the quick slots),
  `henesysmarket_1920x1080_016`, `_026`, `_054` (objects drawn in front),
  `henesyscrowd_1920x1080_018` (a chat balloon).
- **All three `unsure`**: `f002`, `f043`, `f059`.

### Checked by eye

Every frame of `v3` (all 307, so every `v2` frame too) was drawn with the
map's footholds and ropes projected through its `camera`, the `feet` as a
cross and the minimap's position as a ring, beside the difference between
the frame and the static render at that camera (right, the static art
cancels to black). That covers at least 10 frames per map and size where the
set has them, and every frame where the POC's two reads disagree:
`hybrid_tracker`'s fusion (minimap against play area) says `DISAGREE` on 18
frames, and its camera differs from the world tracker's by more than 2 px on
103 (107 frames in all). On every one of them the disagreement was the
hybrid's camera or its own tag pick (another player's tag); the labels are
the world tracker's camera and our tag's feet, and none was corrected
beyond the list above.

The labels are only as true as that check: nobody watched the client for
them, and where the name tag can't be read the feet are `covered`, even when
the character can be seen.

## `v3`'s frames

Captured on 2026-11-09 by the maintainer, at the live client, with
`python -m maple.probe resolution` setting each size.

| Frames | Map | Size | Kept |
| --- | --- | --- | --- |
| `henesys_<size>_00` to `_10` | Henesys, walking right in steps | 800x600, 1024x768, 1280x720, 1366x768, 1920x1200, 2560x1440 | all |
| `henesys_1920x1080_00` to `_12` | Henesys, walking right | 1920x1080 | all |
| `henesysL_1920x1080_00` to `_16` | Henesys, walking left from the right end; the minimap scrolls sideways | 1920x1080 | all |
| `henesysmarket_1920x1080_000` to `_089` | Henesys Market, 1 frame a second; the minimap scrolls sideways | 1920x1080 | 45 |
| `henesyscrowd_1920x1080_000` to `_059` | Henesys channel 1, crowded | 1920x1080 | 30 |
| `ellinia_1920x1080_000` to `_059` | Ellinia, climbing ropes and ladders; the minimap scrolls vertically | 1920x1080 | 25 |

The three 1-frame-a-second sets are near duplicates, so `v3` keeps their
even-numbered frames and, of those, drops a frame whose camera and minimap
reading equal the last kept one's. That dropped the odd frames (45 of
Henesys Market, 30 each of the crowd and Ellinia) and `ellinia_1920x1080_002`
to `_010`, where the character stands still where `_000` shows it.

The 2560x1440 frames are all one camera, with our character at the map's
right end.
