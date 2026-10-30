# Game data

`game_data/` reads MapleStory Classic's client files on disk and extracts them
into a store, so the bot can look up maps, mobs and skills instead of having
them typed in by hand. It never touches the running game. The epic is #259;
its intent and spec are the issue body.

This page covers setting it up, the commands, looking things up in code, the
patch report, rendering a map, composing a scene, and the store's layout, the
catalogue's tables included, for anyone reading it directly.

## On a new machine

`game_data` needs to know where this machine's client data is. Nothing guesses:

1. Copy `configs/game_data.example.ini` to `configs/game_data.ini`. The copy is
   gitignored, because the path is per machine.
2. Set `[Client] Data` to the Classic client's data folder: the `Data` inside
   `MSCW`, not the modern client's `MapleStory\Data` beside it. For a default
   Steam install, it's
   `C:\Program Files (x86)\Steam\steamapps\common\MapleStory\MSCW\Data`.

Any command's `--client PATH` overrides the file. With neither, the command
fails, naming the file to create.

## Commands

```
python -m game_data extract [--client PATH] [--root PATH]
python -m game_data status  [--client PATH] [--root PATH]
python -m game_data report  [OLD NEW] [--root PATH]
python -m game_data show map|mob|skill NAME [--level N] [--root PATH]
python -m game_data search TEXT [--kind map|mob|skill] [--root PATH]
python -m game_data render MAP [--overlays] [--hitboxes] [--scale S] [--out PATH] [--root PATH]
```

`--root` is the store, `data/game_data` by default (gitignored, like all of
`data/`). A relative `--root` is taken from the current directory. Everything
`game_data` writes goes under it.

- **`extract`** extracts the installed client into the store, and builds its
  catalogue. After a patch, running it again is the whole update. It prints
  the build id, how many images and canvases it stored, how many new images it
  added, the catalogue's schema version, and the failures. Extracting the full client takes about 16 minutes, because every
  canvas is decoded and written as a PNG. Re-extracting a Build the store has
  takes seconds.
- **`status`** prints `missing` (no extraction yet), `fresh` (the installed
  client is the latest extraction's Build) or `stale` (it isn't: run
  `extract`). It only `stat`s the archives, so it is quick enough for every
  bot startup. It reads an archive only when its size matches but its
  modification time doesn't, to tell a touched file from a changed one. The
  manifest isn't updated afterwards, so a touched archive is read again on
  every call until the next new extraction.

- **`report [OLD NEW]`** rebuilds the patch report from build `OLD` to build
  `NEW`, and prints its path. With neither, it compares the two kept
  extractions, the older to the latest. `extract` writes the report by itself
  when a new Build lands after another, so this is for rebuilding one, or for
  comparing a pair `extract` didn't. See "The patch report".
- **`show map NAME`** prints one map as JSON: its bounds, flags, footholds,
  ropes, portals and spawns. `NAME` is a name or an ID (see "Looking things
  up"). For example, `show map Henesys`, `show map "Victoria Road: Henesys"`
  or `show map <id>`.
- **`show mob NAME`** prints one mob: its stats, and every frame of every
  action. For example, `show mob Snail`.
- **`show skill NAME`** prints one skill with every level, and
  **`--level N`** only that level, with the actions the skill plays. For
  example, `show skill "Magic Claw" --level 20`. `--level` with `show map` or
  `show mob` is a usage error.
- **`search TEXT`** prints, as JSON, every map, mob and skill whose name
  contains `TEXT`, case aside, with its kind, its ID and its name (a map's
  `street: map name`). `--kind` keeps one kind.

- **`render MAP`** draws a map's full screen and writes it as a PNG, by
  default to `<root>/renders/<map id>.png`, and prints the path. `MAP` is a
  name or an ID. `--overlays` adds footholds, ropes, portals and spawns,
  `--hitboxes` adds each spawn's body hitbox, `--scale S` multiplies both sides
  by `S`, and `--out PATH` writes elsewhere. See "Rendering a map".

`show`, `search` and `render` read the latest extraction's catalogue, and need
no client.

**Errors.** When the client path isn't set or isn't a folder, an archive
doesn't read, the store isn't as expected, a name names nothing or several
things, or a skill has no such level, a command prints a one-line
message on stderr and exits with 1. Any other failure, such as a full disk or a
file another program holds open, ends with a Python traceback and exit code 1.
An `extract` that fails before its new extraction is renamed into place leaves
the existing extractions and images as they were (see "The store"). One that
fails during retention, after the rename, can leave an older extraction half
deleted: on Windows, `rmtree` stops at a file another program holds open.

The same functions, for code: `game_data.extraction.extract(client, root)` and
`status(client, root)`. `extract` builds no catalogue unless it's given the
hook, `catalogue=game_data.catalogue.build_catalogue`, as the command does. Every entry point takes the store root. **Tests and
`client_files` runs pass a temporary root, never the real store**, because
extracting deletes old extractions. No test extracts the whole client:
`pytest -m client_files` extracts slices of it (several minutes, most of it
decoding the maps' and skills' canvases), and the default run uses synthetic
clients only.

## Looking things up

```python
from game_data.catalogue import Catalogue

with Catalogue.latest() as cat:           # or Catalogue.open(build_id, root=...)
    henesys = cat.map("Henesys")           # MapData; or cat.map(map_id)
    layers = cat.map_layers("Henesys")     # tuple[MapLayer, ...], with frames
    snail = cat.mob("Snail")               # MobData: stats and frames
    claw = cat.skill("Magic Claw")         # SkillData, with every level
    level = claw.level(20)                 # SkillLevel, with the skill's actions
    cat.action_duration("swingO1")         # int: milliseconds
    cat.skill_duration("Magic Claw")       # int: its first action's
    cat.maps_spawning("Snail")             # list[MapRef]: id, name, spawns
    found = cat.search("henes")            # list[Ref]: kind, id, name
    physics = cat.physics()                # dict[str, float]
    cat.item_icons()                       # tuple[ItemIcon, ...], by item
    cat.meso_frames()                      # tuple[MesoFrame, ...]
    cat.damage_digits()                    # tuple[DamageDigit, ...]
```

`latest` and `open` take the store root (`root=`, `data/game_data` by
default). Every lookup returns frozen dataclasses (`game_data.catalogue.model`)
in virtual coordinates. A catalogue holds its file open until it's closed, so
use it in a `with`.

**Names first, IDs accepted.** A map, mob or skill lookup takes a name or an
ID, as an `int` or a string of digits, and looks among its own kind only. A
name matches whole, case aside, and a map's also matches as
`street: map name`, because many maps share a name:

- a name that matches one gives it;
- a name that matches several raises `LookupError`, listing each with its ID,
  a map as `street: map name (id)`. Nothing is picked for you: two skills
  named MP Eater are asked for by ID;
- a name that matches none raises `LookupError`, listing up to five of the
  closest names (`difflib.get_close_matches`).

`skill(...).level(n)` raises `LookupError` for a level the skill doesn't have.
`action_duration` raises it for an action the character doesn't have, or one
none of whose frames has a delay (`prone`, `sit`, `dead`), and
`skill_duration` for a skill that plays no action, as passive skills don't.

**A catalogue is rebuilt when it's out of date.** Opening an extraction whose
manifest has another `catalogue_schema_version`, or which has no catalogue,
rebuilds it from `raw.sqlite` first, and updates the manifest. That needs the
store only, not the client.

## The patch report

`reports/<old>__<new>.html` is one self-contained page: inline CSS and SVG,
with sprites embedded as `data:` URIs. It opens with no network, and survives
retention deleting the extractions it was made from. It is written when
`extract` lands a new Build after another extraction, and `extract` prints its
path. It has:

- a table of counts: maps, mobs, skills and raw images, added, removed and
  changed;
- **maps** added and removed, and the maps whose geometry changed: VR bounds,
  footholds, ropes, portals and spawns, each change listed, with the map drawn
  before and after (what is gone or different is red, what is new or different
  is green);
- **mobs** added and removed, and the mobs whose stats changed, with their
  sprite (first `stand` frame) before and after;
- **skills** added and removed, and the levels added, removed or changed, field
  by field;
- the **raw differences**, collapsed: images added or removed, and for a changed
  image the nodes that differ, each with its path, old value and new value. A
  canvas whose pixels changed shows as a changed `image` (its hash). A real
  patch can change thousands of images, so only the first 300 changed images
  and 40 nodes of each are listed, and the page says how many it left out.

Everything is named through the client's `strings`; a thing it names nowhere is
told by its ID. A raw difference is judged by the `sha256` of an image's stored
tree, so it sees what the typed summary doesn't read (a map's background, a
mob's sprite).

Reading the page is for the maintainer, on the next real patch. Only that tells
whether it reads well.

## Rendering a map

```python
from pathlib import Path

from game_data.catalogue import Catalogue
from game_data.render import render_map, write_png

with Catalogue.latest() as cat:
    screen = render_map(cat, "Henesys", overlays=True)   # RGBA numpy array
    write_png(screen, Path("henesys.png"))
```

`render_map(cat, map, *, scale=1.0, frame=0, viewport=(1366, 768),
camera=None, images=None, overlays=False, hitboxes=False)` draws a map in virtual coordinates. The VR
bounds' top left is pixel (0, 0), and the image is the bounds' size times
`scale`. It reads the catalogue and the image store only, never the client.

- **Draw order.** First the backgrounds behind, by number. Then layers 0 to 7:
  in each, its objects by `z`, then its tiles by their canvas's `z`, with ties
  kept in the map's order. Then the backgrounds in front. Each item puts its
  frame's `origin` at its position. A flipped item mirrors about its position.
- **Animated items** are drawn at `frame % frame_count`.
- **Backgrounds** are placed for a camera of `viewport`'s size centred on the
  map, as the client does, or for `camera` when one is given (a scene's). A background moves by `(rx + 100) / 100` of the
  camera's centre: `rx = -100` is fixed to the map, and `rx = 0` is fixed to
  the camera, as a sky is. Likewise `ry`. A background whose type tiles is
  repeated every `cx` (or `cy`, or its size when that's 0) across the whole
  map, not only the viewport. Types 4 to 7 also scroll over time, which a
  still render doesn't show.
  `game_data.render.STORED_AT_RX` holds which `rx` is fixed to the map, and is
  the one line to change if renders show the other reading is right.
- **Overlays** are drawn after scaling, one pixel wide. They are the map's own
  footholds (white), footholds on tiles (blue) and on objects (green), the
  map's own ropes (cyan) and ropes on objects (yellow), and portals (red
  dots). Each mob spawn is drawn as its mob's first `stand` frame (`fly` when
  it has no `stand`) where it stands, `(x, cy)`. NPCs, and mobs with no frame
  to draw, get an orange dot. `hitboxes=True` draws the spawns and their
  `lt`/`rb` boxes in magenta, with or without the other overlays.

Whether a render looks like the game can't be tested offline: a person
compares renders against in-game screenshots.

## Composing a scene

```python
import numpy as np

from game_data.catalogue import Catalogue
from game_data.scenes import compose_scene

with Catalogue.latest() as cat:
    rng = np.random.default_rng(42)
    scene = compose_scene(cat, "Henesys Hunting Ground I", rng)
    scene.image              # (768, 1366, 3) RGB
    scene.labels             # tuple[Label(cls, box, visible), ...]
```

`compose_scene(cat, map, rng, *, client=(1366, 768), mobs=(0, 15),
visibility_floor=0.3, cameras=None, occluders=None)` is one synthetic client
screen of a map, with its mobs drawn on their spawns, and what the client
draws over them, for training a detection model on. It reads the catalogue
and the image store, never the client, and knows nothing of YOLO or
`ml_training`. Players and the UI aren't drawn.

- **The view.** A camera of `client`'s size. On an axis where the VR bounds
  are at least that size, its centre is drawn uniformly in them, then clamped
  so the view stays inside, so views flush with an edge come up more often
  than others. On an axis where the map is smaller, it's centred and the rest
  is black, as the client shows it. The background is `render_map` at that
  camera, so backgrounds' parallax follows it, cropped. Every animated item is
  at one `frame` drawn for the scene.
- **Render reuse.** `cameras=None` renders the map for every scene, which on a
  large map is most of a scene's time. `cameras=n` renders `n` cameras of the
  map once, the first time an `rng` composes it, and each scene then picks
  one. The views are held for as long as that `rng` is.
- **The mobs.** Their number is drawn from `mobs`, both ends included. Each
  comes from a spawn drawn uniformly among the map's `mob` spawns whose
  `[rx0, rx1]` overlaps the view's columns: its species, `x` uniform in
  `[rx0, rx1]`, and `y` its foothold's height at `x`. When the range runs past
  that foothold, the height is the first foothold along its `prev`/`next`
  chain that spans `x` (walls skipped). A mob with a `fly_speed` is raised by
  0 to 150 pixels, no higher than the view's top. Its action is drawn among
  those it has of `stand`, `move`, `hit1`, `die1`, its frame uniformly, and it
  faces either way. The mobs are drawn in a random order.
- **Occluders.** `occluders` maps each kind to draw to the fewest and most of
  it per scene, both included, such as `{"drops": (0, 8), "damage": (0, 4)}`.
  A kind left out is off, and `None`, the default, draws none. The kinds are
  `game_data.scenes.OCCLUDERS`.
  - `drops` lie on a spawn drawn as a mob's is, `x` uniform in its
    `[rx0, rx1]`, on its foothold's height there. Half are mesos, at a frame
    of their spin drawn uniformly; the rest are item icons, drawn uniformly
    among the `Consume`, `Etc` and `Install` items (not `Cash`). An icon is
    placed as in a 32-pixel inventory slot centred on `x`, its bottom on the
    ground, which is where its `origin` puts it. Each drop is behind or in
    front of the mobs at random.
  - `damage` numbers are above a mob with a pixel in the view, drawn
    uniformly among them: its frame's `head` (mirrored when it faces the
    other way), or else the middle of its opaque pixels' top. A number's bottom is 0 to 60 pixels above that,
    and it's centred there. It has 1 to 6 digits, the first never 0, from a
    pair of digit sets of `NoRed` or `NoCri`: `<set><2k + 1>` for the first
    digit, `<set><2k>` for the rest, each overlapping the one before by 8
    pixels. Numbers are in front of everything.

  A kind the catalogue has no sprites for is left out, with a warning. The
  constants (the share of mesos, the slot, the rise, the overlap) are first
  guesses, in `game_data/scenes/occluders.py`, to be judged by eye.
- **Labels.** `Label(cls, box, visible)`. `box` is `(x1, y1, x2, y2)` in the
  view's pixels, `x2` and `y2` one past the last: the bounds of the drawn
  sprite's opaque pixels (alpha > 0) inside the view, not its `lt`/`rb`
  hitbox. `visible` is the share of those pixels that nothing drawn after it
  covers: a mob, a drop in front, or a damage number. A label under `visibility_floor` is dropped; the mob stays in the
  image. A mob with no pixel in the view has no label.
- **Class names** are the catalogue's mob names with spaces and dots removed
  (`class_name`), the form the bot's `_is_detectable_by_model` compares. Two
  species of one class name in a map raise `SceneError`, naming both IDs. A
  species the catalogue lacks, with no name, or with no frame of those four
  actions that has an image, is left out, with a warning naming it.
- **Determinism.** Every draw comes from `rng`, in a fixed order: the same
  catalogue build, map, arguments and seed give the same pixels and labels.
  `SCENES_VERSION` changes whenever that output would.

`draw_mobs(view, placements, images, overlays=())` is the step that draws: it
lays each `Placement(mob, action, frame, x, y, flip)` over an RGB view, its
origin at view pixel `(x, y)`, then each `Overlay(pixels, left, top)` over
them, and returns one label per placement, unfloored (`None` for a mob
outside the view), the overlays counted against `visible`. Tests place mobs
through it directly.

Whether scenes look like the game (views, placement, parallax, occluders) is
the maintainer's to judge, by eye, on the extract.

## The store

```
data/game_data/
  extractions/<build-id>/
    manifest.json          the Build, and how it was extracted
    raw.sqlite             every image's tree, losslessly
    catalogue.sqlite       the typed layer, built from raw.sqlite
  images/<hh>/<name>.png   every canvas's pixels, shared by all extractions
  reports/<old>__<new>.html  the patch reports
  renders/<map id>.png     what `render` writes by default
```

### Builds and extractions

A **Build** is one version of the installed client's files. Its **build id**
is the first 16 hex digits of a SHA-256 over every archive's
`(path, size, sha256)`, sorted by path. The archives are every `.wz` under
`Data` and every `.ms` in `Data/Packs`. Where the client is installed, and the
files' modification times, don't change the id.

An **Extraction** is one Build's extracted data: one folder under
`extractions/`. The **latest** is the one with the newest `extracted_at`.

- Extracting a Build the store already has creates nothing. It refreshes that
  extraction's `extracted_at`, so it becomes the latest. That's how a rollback
  works.
- An extraction is written to a hidden folder in `extractions/` and renamed
  when it's complete. One that fails is deleted, and the existing extractions
  and images are left byte-identical.
- **Retention.** After each extraction, the two latest extractions are kept and
  any older one is deleted. So are the images no kept extraction names (which
  includes the images a failed run wrote) and the reports that name an
  extraction no longer kept.
- Only one `extract` may run on a store at a time.

### `manifest.json`

| key                        | what                                                              |
| -------------------------- | ----------------------------------------------------------------- |
| `build`                    | the build id                                                      |
| `extractor_version`        | the version of the code that wrote `raw.sqlite`                   |
| `catalogue_schema_version` | the catalogue's schema version, `null` if none was built          |
| `extracted_at`             | when it was last extracted, ISO 8601 in UTC                       |
| `archives`                 | by path from `Data`: `size`, `mtime_ns`, `sha256`                 |
| `images`, `canvases`       | how many images `raw.sqlite` holds, and how many canvases in them |
| `failures`                 | canvases whose pixels couldn't be found: `image`, `node`, `reason` |

**Failures.** One thing doesn't stop an extraction: a canvas whose `_outlink`
or `_inlink` names nothing. The client has one, an icon under
`Character/Weapon`. Each is listed here and in `extract`'s output, and its
canvas is stored with `"image": null`. Any other problem, such as an archive
that doesn't parse or a pixel format nobody knows, stops the extraction and
names the archive, image and node.

### `raw.sqlite`

```sql
images(path TEXT PRIMARY KEY, sha256 TEXT, tree TEXT)
canvas_images(name TEXT PRIMARY KEY)
```

`images` has one row per image in the client, such as
`Map/Map/Map0/000001000.img`. `tree` is its property tree as JSON, and
`sha256` is the SHA-256 of that text, so two extractions' rows differ exactly
when their trees do. `canvas_images` lists every image in the image store that
the canvases name. Retention uses it.

The JSON keeps every node's name, type, value and order. The common types are
plain JSON, and the rest are objects tagged with `$type`:

| node         | JSON                                                                  |
| ------------ | --------------------------------------------------------------------- |
| sub-property | an object of its children, in the client's order                      |
| int          | `5`                                                                   |
| double       | `5.0`: always written with a fraction, so it reads back as a float    |
| string       | `"Henesys"`                                                           |
| null         | `null`                                                                |
| short        | `{"$type": "short", "value": 5}`                                      |
| long         | `{"$type": "long", "value": 5}`                                       |
| float        | `{"$type": "float", "value": 0.5}`                                    |
| vector       | `{"$type": "vector", "x": 1, "y": 2}`                                 |
| UOL          | `{"$type": "uol", "path": "../0"}`: the link, not what it leads to    |
| canvas       | `{"$type": "canvas", "image": "<name>", "w": 40, "h": 30, ...}`       |
| convex       | `{"$type": "convex", "0": <vector>, "1": <vector>, ...}`              |
| sound        | `{"$type": "sound", "duration_ms": 1500, "length": 30, "sha256": "…"}` |
| raw data     | `{"$type": "raw_data", "length": 16, "sha256": "…", ...}`             |

- **A canvas** is its image's name in the image store, that image's width and
  height, then the canvas's own properties (`origin`, `delay`, `lt`, `_hash`,
  `_outlink`...) as further keys. Most of the client's canvases are 1x1
  placeholders whose pixels are elsewhere, through `_outlink` or `_inlink`.
  `image`, `w` and `h` are the pixels the links lead to, and the properties
  stay those of the placeholder.
- **Sounds** are references: never decoded, only their length, duration and
  the SHA-256 of their bytes, so a changed sound shows.
- **Raw data** is the client's colour lookup tables and a font, likewise kept
  as a length and a SHA-256.

An object is a sub-property exactly when it has no `$type` key. No node in the
client is named `$type`, and no canvas has a child named `image`, `w` or `h`.
If one ever does, extraction stops rather than store something ambiguous.

### `catalogue.sqlite`

The typed layer: one row per map, foothold, rope, portal, spawn and layer
item, mob and mob frame, skill and skill level, character action frame, item
icon, meso frame and damage digit, read from `raw.sqlite` and nothing else. Code reads it through
`Catalogue` ("Looking things up"); anyone may query it directly with any
SQLite tool. Its tables and columns are stable within a schema version, the
`catalogue_schema_version` in the manifest (and the file's `user_version`).
Changing them bumps the version. A test holds this list and the schema
together.

Everything is in **virtual coordinates**, the map's own. An ID is an integer,
so the client's `000000100` is `100`. Booleans are 0 or 1. A flag the client
leaves out, such as `town` or a spawn's `f`, is 0. Where a column says NULL,
the client has no value there.

Where it comes from: `String/Map.img`, `String/Mob.img`, `String/Npc.img`
and `String/Skill.img` for `strings`; each `Map/Map/Map<n>/<id>.img`, and the
`Map/Obj`, `Map/Tile` and `Map/Back` images it draws from, for the map tables;
`Map/Physics.img` for `physics`; each `Mob/<id>.img` for `mobs` and
`mob_frames` (Classic keeps them in `Packs/Mob_00000.ms`); each job's
`Skill/<job>.img` for `skills` and `skill_levels` (`Skill/Attacktype.img`,
`Skill/ItemSkill.img` and `Skill/MobSkill/` aren't read); and the body,
`Character/00002000.img`, for `actions`; each `Item/<category>/<prefix>.img`
for `item_icons`, `Item/Special/0900.img` for `meso_frames`, and
`Effect/BasicEff.img` for `damage_digits`. A client without one of these leaves its tables empty. One that is
there but isn't as expected stops the build, naming the image and the node,
and the extraction with it.

#### `strings`

| column        | type    | what                                                |
| ------------- | ------- | --------------------------------------------------- |
| `kind`        | TEXT    | `map`, `mob`, `npc` or `skill`                      |
| `id`          | INTEGER | the map's, mob's, NPC's or skill's ID               |
| `name`        | TEXT    | its name; a map's is `mapName`, without its street  |
| `description` | TEXT    | a map's `mapDesc`, a skill's `desc`; NULL otherwise |

`String/Skill.img` also names each job's skill book (`bookName`); those
entries aren't skills, and aren't here.

#### `maps`

| column             | type    | what                                                                 |
| ------------------ | ------- | -------------------------------------------------------------------- |
| `id`               | INTEGER | the map's ID                                                         |
| `name`             | TEXT    | from `strings`; NULL when `String/Map.img` doesn't name it           |
| `street`           | TEXT    | its `streetName`; likewise                                           |
| `vr_left`          | INTEGER | the VR bounds, the box the camera stays in                           |
| `vr_top`           | INTEGER |                                                                      |
| `vr_right`         | INTEGER |                                                                      |
| `vr_bottom`        | INTEGER |                                                                      |
| `vr_derived`       | INTEGER | 1 when the map has no VR bounds, and these are its footholds' extent |
| `minimap_center_x` | INTEGER | `miniMap/centerX`; this and the next four are NULL with no minimap   |
| `minimap_center_y` | INTEGER | `miniMap/centerY`                                                    |
| `minimap_mag`      | INTEGER | `miniMap/mag`: the minimap is the map scaled down by `2**mag`        |
| `minimap_width`    | INTEGER | `miniMap/width`, in virtual pixels                                   |
| `minimap_height`   | INTEGER | `miniMap/height`                                                     |
| `town`             | INTEGER | 1 for a town                                                         |
| `swim`             | INTEGER | 1 for a map the character swims in                                   |
| `fly`              | INTEGER | 1 for a map the character flies in                                   |
| `field_limit`      | INTEGER | `fieldLimit`, the client's bit field of what the map forbids         |
| `bgm`              | TEXT    | the music, such as `Bgm00/<name>`; NULL when it has none             |
| `return_map`       | INTEGER | `returnMap`; NULL for none (the client's `999999999`)                |

The VR bounds derived from footholds are the map's own footholds' extent, with
no margin added.

#### `footholds`

| column     | type    | what                                                                    |
| ---------- | ------- | ----------------------------------------------------------------------- |
| `map`      | INTEGER | the map                                                                 |
| `source`   | TEXT    | `map` for the map's own; `object` or `tile` for one drawn on that item  |
| `layer`    | INTEGER | the map's `foothold/<layer>/...`; NULL for `object` and `tile`          |
| `group_id` | INTEGER | the group, `foothold/<layer>/<group>/...`; likewise                     |
| `id`       | INTEGER | the foothold's ID; for `object` and `tile`, a running number in the map |
| `x1`       | INTEGER | one end                                                                 |
| `y1`       | INTEGER |                                                                         |
| `x2`       | INTEGER | the other                                                               |
| `y2`       | INTEGER |                                                                         |
| `prev`     | INTEGER | the foothold before it, 0 for none; NULL for `object` and `tile`        |
| `next`     | INTEGER | the foothold after it; likewise                                         |

An object's or tile's footholds are polylines relative to its position, and
each segment is a row, placed. A flipped object's are mirrored about its
position. Three objects in the client are rotated (`r`); their footholds are
stored unrotated, because what `r` does to them isn't known.

#### `ropes`

| column                 | type    | what                                                               |
| ---------------------- | ------- | ------------------------------------------------------------------ |
| `map`                  | INTEGER | the map                                                            |
| `source`               | TEXT    | `map` for the map's `ladderRope`, `object` for one drawn on one    |
| `id`                   | INTEGER | the rope's ID; for `object`, a running number in the map           |
| `x`                    | INTEGER | the vertical line it is                                            |
| `y1`                   | INTEGER | its top                                                            |
| `y2`                   | INTEGER | its bottom                                                         |
| `ladder`               | INTEGER | `l`: 1 for a ladder, 0 for a rope; NULL for `object`               |
| `usable_from_foothold` | INTEGER | `uf`: whether it can be climbed off at its top; NULL for `object`  |
| `page`                 | INTEGER | the depth the character is drawn at on it; NULL for `object`       |

#### `portals`

| column          | type    | what                                                |
| --------------- | ------- | --------------------------------------------------- |
| `map`           | INTEGER | the map                                             |
| `name`          | TEXT    | `pn`; spawn points are `sp`                         |
| `type`          | INTEGER | `pt`, the client's portal type (0 is a spawn point) |
| `x`             | INTEGER |                                                     |
| `y`             | INTEGER |                                                     |
| `target_map`    | INTEGER | `tm`; NULL for none (the client's `999999999`)      |
| `target_portal` | TEXT    | `tn`, the portal it leads to there; NULL for none   |

#### `spawns`

| column         | type    | what                                         |
| -------------- | ------- | -------------------------------------------- |
| `map`          | INTEGER | the map                                      |
| `kind`         | TEXT    | `mob` or `npc`                               |
| `id`           | INTEGER | the mob's or NPC's ID, which `strings` names |
| `x`            | INTEGER |                                              |
| `cy`           | INTEGER | the y of the foothold it stands on           |
| `foothold`     | INTEGER | `fh`, that foothold's ID                     |
| `rx0`          | INTEGER | the left of the range it moves in            |
| `rx1`          | INTEGER | the right                                    |
| `respawn_time` | INTEGER | `mobTime`; NULL when the map doesn't set it  |
| `flip`         | INTEGER | `f`: 1 when it faces the other way           |
| `hidden`       | INTEGER | `hide`                                       |

#### `map_layers`

One row per tile, object and background, in the map's order: each layer's
objects, then its tiles, from layer 0 to 7, then the backgrounds.

| column        | type    | what                                                                          |
| ------------- | ------- | ----------------------------------------------------------------------------- |
| `item`        | INTEGER | the row's own number, which `layer_frames` names                              |
| `map`         | INTEGER | the map                                                                       |
| `kind`        | TEXT    | `tile`, `object` or `back`                                                    |
| `layer`       | INTEGER | 0 to 7 for a tile or object; NULL for a background                            |
| `z`           | INTEGER | an object's `z`, a tile's canvas `z`, a background's number in `back`         |
| `zm`          | INTEGER | the map's `zM` for a tile or object; NULL for a background                    |
| `x`           | INTEGER | the position, raw: the frame's origin is drawn there                          |
| `y`           | INTEGER |                                                                               |
| `flip`        | INTEGER | `f`; 0 for a tile                                                             |
| `origin_x`    | INTEGER | the first frame's origin; NULL when it has no frames                          |
| `origin_y`    | INTEGER |                                                                               |
| `frame_count` | INTEGER | how many rows it has in `layer_frames`                                        |
| `asset`       | TEXT    | the node it's drawn from, such as `Map/Tile/<tS>.img/<u>/<no>`; NULL for none |
| `type`        | INTEGER | a background's `type`, how it tiles and scrolls; NULL for a tile or object    |
| `rx`          | INTEGER | a background's parallax, `rx`; likewise                                       |
| `ry`          | INTEGER | `ry`                                                                          |
| `cx`          | INTEGER | a background's tiling distance, `cx`; likewise                                |
| `cy`          | INTEGER | `cy`                                                                          |
| `a`           | INTEGER | a background's opacity, 0 to 255; likewise                                    |
| `front`       | INTEGER | 1 for a background drawn in front; likewise                                   |

A background with no image (an empty `bS`) has no asset and no frames.

#### `layer_frames`

| column     | type    | what                                                           |
| ---------- | ------- | -------------------------------------------------------------- |
| `item`     | INTEGER | its `map_layers` row                                           |
| `frame`    | INTEGER | the frame's number, from 0                                     |
| `image`    | TEXT    | its image in `images/`; NULL when its pixels couldn't be found |
| `origin_x` | INTEGER | the frame's origin: the pixel drawn at the item's position     |
| `origin_y` | INTEGER |                                                                |
| `delay`    | INTEGER | how long it's shown, in milliseconds; NULL when it doesn't say |

#### `physics`

| column  | type | what                                         |
| ------- | ---- | -------------------------------------------- |
| `key`   | TEXT | a `Map/Physics.img` key, such as `walkSpeed` |
| `value` | REAL | its value                                    |

#### `mobs`

| column         | type    | what                                                                    |
| -------------- | ------- | ----------------------------------------------------------------------- |
| `id`           | INTEGER | the mob's ID; the client's `0100100` is `100100`                        |
| `name`         | TEXT    | from `strings`; NULL when `String/Mob.img` doesn't name it              |
| `link`         | INTEGER | `info/link`: the mob whose sprites it shares; NULL when it has its own  |
| `level`        | INTEGER | `level`                                                                 |
| `max_hp`       | INTEGER | `maxHP`                                                                 |
| `max_mp`       | INTEGER | `maxMP`                                                                 |
| `speed`        | INTEGER | `speed`, as the client gives it (often negative); NULL when it has none |
| `fly_speed`    | INTEGER | `flySpeed`; NULL for a mob that doesn't fly                             |
| `exp`          | INTEGER | `exp`; NULL when it has none                                            |
| `pa_damage`    | INTEGER | `PADamage`, its physical attack, what touching it does                  |
| `ma_damage`    | INTEGER | `MADamage`, its magic attack                                            |
| `pd_damage`    | INTEGER | `PDDamage`, its physical defence                                        |
| `md_damage`    | INTEGER | `MDDamage`, its magic defence                                           |
| `acc`          | INTEGER | `acc`, its accuracy                                                     |
| `eva`          | INTEGER | `eva`, its avoidability                                                 |
| `pushed`       | INTEGER | `pushed`: the damage that knocks it back                                |
| `body_attack`  | INTEGER | `bodyAttack`: 1 when touching it hurts                                  |
| `boss`         | INTEGER | `boss`                                                                  |
| `undead`       | INTEGER | `undead`                                                                |
| `first_attack` | INTEGER | `firstAttack`: 1 when it attacks before it's attacked                   |
| `elem_attr`    | TEXT    | `elemAttr`, its elements as the client writes them; NULL for none       |

#### `mob_frames`

One row per frame of each of a mob's actions (`stand`, `move`, `hit1`,
`attack1`...), in the image's order. A mob with a `link` has the linked mob's
frames under its own ID, so this table answers for it directly.

| column     | type    | what                                                              |
| ---------- | ------- | ----------------------------------------------------------------- |
| `mob`      | INTEGER | the mob                                                           |
| `action`   | TEXT    | the action, such as `stand`                                       |
| `frame`    | INTEGER | the frame's number, from 0                                        |
| `image`    | TEXT    | its image in `images/`; NULL when its pixels couldn't be found    |
| `origin_x` | INTEGER | the frame's origin: the pixel drawn at the mob's position         |
| `origin_y` | INTEGER |                                                                   |
| `lt_x`     | INTEGER | the body hitbox's top left, `lt`, relative to the mob's position  |
| `lt_y`     | INTEGER | NULL, like the next four, when the frame has none                 |
| `rb_x`     | INTEGER | the body hitbox's bottom right, `rb`                              |
| `rb_y`     | INTEGER |                                                                   |
| `head_x`   | INTEGER | where its head is, `head`                                         |
| `head_y`   | INTEGER |                                                                   |
| `delay`    | INTEGER | how long it's shown, in milliseconds; NULL when it doesn't say    |

A frame that's a UOL to another frame of the image is stored as the frame it
leads to. Whether the hitboxes line up with the game is to be checked by eye
(#259).

#### `skills`

| column        | type    | what                                                                     |
| ------------- | ------- | ------------------------------------------------------------------------ |
| `id`          | INTEGER | the skill's ID, such as `2001003`                                        |
| `job`         | INTEGER | the job whose image it's in, `Skill/<job>.img`, such as `200`            |
| `name`        | TEXT    | from `strings`; NULL when `String/Skill.img` doesn't name it             |
| `description` | TEXT    | its `desc` there; likewise                                               |
| `type`        | INTEGER | `info/type`; NULL when it has none                                       |
| `max_level`   | INTEGER | how many levels it has in `skill_levels`                                 |
| `actions`     | TEXT    | the character actions it plays, a JSON array such as `["swingO1"]`       |
| `icon`        | TEXT    | its `icon` in `images/`; NULL when it has none                           |

#### `skill_levels`

One row per level of each skill. A skill's `common` fields hold at every
level, so they're in every level's row, as if each level had them. A skill
with only `common` has `common/maxLevel` levels of them.

| column         | type    | what                                                                   |
| -------------- | ------- | ---------------------------------------------------------------------- |
| `skill`        | INTEGER | the skill                                                              |
| `level`        | INTEGER | the level, from 1                                                      |
| `mp_con`       | INTEGER | `mpCon`, its MP cost; NULL, like every column below, when not set      |
| `time`         | INTEGER | `time`, how long it lasts, in seconds                                  |
| `lt_x`         | INTEGER | `lt` and `rb`: the box it reaches, relative to the character           |
| `lt_y`         | INTEGER |                                                                        |
| `rb_x`         | INTEGER |                                                                        |
| `rb_y`         | INTEGER |                                                                        |
| `mob_count`    | INTEGER | `mobCount`, how many mobs it hits                                      |
| `attack_count` | INTEGER | `attackCount`, how many times it hits each                             |
| `range`        | INTEGER | `range`                                                                |
| `cooltime`     | INTEGER | `cooltime`, its cooldown, in seconds                                   |
| `other`        | TEXT    | every other field, a JSON object by the client's names, such as `mad`  |

In `other`, an integer of any type, or a string of digits, is a number; a
vector is `{"x", "y"}`; anything else, such as a level's animation, is as
`raw.sqlite` has it. Many attack skills have neither `lt`/`rb` nor `range`:
Magic Claw is one. Their reach isn't in the skill's data.

#### `actions`

The character's actions, from the body, `Character/00002000.img`: one row per
frame.

| column     | type    | what                                                                       |
| ---------- | ------- | -------------------------------------------------------------------------- |
| `action`   | TEXT    | the action, such as `swingO1`                                              |
| `frame`    | INTEGER | the frame's number, from 0                                                 |
| `delay`    | INTEGER | its `delay` in milliseconds, as the client gives it; NULL when it has none |
| `duration` | INTEGER | the action's: its frames' delays added up; NULL when none has one          |

Some actions borrow other actions' poses, and give some frames a negative
delay (`alert3`, `magic1`...). `duration` adds each delay's magnitude, so it's
how long the action is shown. What the sign means isn't known here, and
`delay` keeps it as the client gives it.

#### `item_icons`

One row per item with an icon, from each `Item/<category>/<prefix>.img`
(`Item/Consume/0200.img`...): its `info/iconRaw`, the icon a drop of it shows.
An item with no `info/iconRaw` has no row. The pets' images,
`Item/Pet/<id>.img`, aren't read; nor are equipment's, which are in
`Character`.

| column     | type    | what                                                                  |
| ---------- | ------- | --------------------------------------------------------------------- |
| `item`     | INTEGER | the item's ID, such as `2000000`                                      |
| `category` | TEXT    | its image's folder: `Consume`, `Etc`, `Install`, `Cash`...            |
| `image`    | TEXT    | its icon in `images/`; NULL when its pixels couldn't be found         |
| `origin_x` | INTEGER | the icon's origin, as in an inventory slot: `(-3, 30)` for a 27x27    |
| `origin_y` | INTEGER |                                                                       |

An `iconRaw` that's a UOL to another item's is stored as the icon it leads
to.

#### `meso_frames`

One row per frame of each meso sprite's spin, `Item/Special/0900.img`'s
`<id>/iconRaw/<n>`. Classic has eight sprites, `9000000` to `9000007`, of 4 or
10 frames.

| column     | type    | what                                                          |
| ---------- | ------- | ------------------------------------------------------------- |
| `meso`     | INTEGER | the sprite's ID, such as `9000000`                            |
| `frame`    | INTEGER | the frame's number, from 0                                    |
| `image`    | TEXT    | its image in `images/`; NULL when its pixels couldn't be found |
| `origin_x` | INTEGER | the frame's origin, as an item icon's                         |
| `origin_y` | INTEGER |                                                               |

#### `damage_digits`

One row per digit of each set the client draws numbers with,
`Effect/BasicEff.img`'s `No<colour><n>` (`NoRed0`, `NoCri1`, `NoViolet0`...).
A set's other children, such as `Miss` or `effect`, aren't digits. In
Classic, `NoRed` and `NoCri` come in pairs, `0`/`1` and `2`/`3`, the odd set
the larger; scenes draw a number's first digit from the odd set and the rest
from the even one. That this is how the client draws them, and which colour
shows what, aren't checked here.

| column      | type    | what                                                          |
| ----------- | ------- | ------------------------------------------------------------- |
| `digit_set` | TEXT    | the set, such as `NoRed0`                                     |
| `digit`     | INTEGER | 0 to 9                                                        |
| `image`     | TEXT    | its image in `images/`; NULL when its pixels couldn't be found |
| `origin_x`  | INTEGER | the digit's origin: about its bottom middle                   |
| `origin_y`  | INTEGER |                                                               |

### `images/`

Every canvas's pixels, as an RGBA PNG at `images/<first two hex>/<name>.png`.
The name is the client's `_hash` when the canvas carries one (mob and skill
frames do). Otherwise it's the SHA-256 of the decoded RGBA pixels, preceded by
the width and height. An image is decoded and written once, and is never
rewritten: a new extraction adds only the images that are new.
