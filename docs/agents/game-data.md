# Game data

`game_data/` reads MapleStory Classic's client files on disk and extracts them
into a store, so the bot can look up maps, mobs and skills instead of having
them typed in by hand. It never touches the running game. The epic is #259;
its intent and spec are the issue body.

This page covers setting it up, the commands, looking things up in code, and
the store's layout, the catalogue's tables included, for anyone reading it
directly. Later tickets add mobs and skills, the patch report and the renderer.

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
python -m game_data show map NAME [--root PATH]
python -m game_data search TEXT [--kind map] [--root PATH]
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

- **`show map NAME`** prints one map as JSON: its bounds, flags, footholds,
  ropes, portals and spawns. `NAME` is a name or an ID (see "Looking things
  up"). For example, `show map Henesys`, `show map "Victoria Road: Henesys"`
  or `show map <id>`.
- **`search TEXT`** prints, as JSON, every map whose name contains `TEXT`, case
  aside, with its ID and its `street: map name`.

`show` and `search` read the latest extraction's catalogue, and need no client.

**Errors.** When the client path isn't set or isn't a folder, an archive
doesn't read, the store isn't as expected, or a name names no map or several,
a command prints a one-line
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
`pytest -m client_files` extracts a small slice of it (about 40 seconds), and
the default run uses synthetic clients only.

## Looking things up

```python
from game_data.catalogue import Catalogue

with Catalogue.latest() as cat:           # or Catalogue.open(build_id, root=...)
    henesys = cat.map("Henesys")           # MapData; or cat.map(map_id)
    layers = cat.map_layers("Henesys")     # tuple[MapLayer, ...], with frames
    found = cat.search("henes")            # list[Ref]: kind, id, name
    physics = cat.physics()                # dict[str, float]
```

`latest` and `open` take the store root (`root=`, `data/game_data` by
default). Every lookup returns frozen dataclasses (`game_data.catalogue.model`)
in virtual coordinates. A catalogue holds its file open until it's closed, so
use it in a `with`.

**Names first, IDs accepted.** A lookup takes a name or an ID, as an `int` or a
string of digits. A name matches whole, case aside, and a map's also matches as
`street: map name`, because many maps share a name:

- a name that matches one map gives it;
- a name that matches several raises `LookupError`, listing each as
  `street: map name (id)`. Nothing is picked for you;
- a name that matches none raises `LookupError`, listing up to five of the
  closest names (`difflib.get_close_matches`).

**A catalogue is rebuilt when it's out of date.** Opening an extraction whose
manifest has another `catalogue_schema_version`, or which has no catalogue,
rebuilds it from `raw.sqlite` first, and updates the manifest. That needs the
store only, not the client.

## The store

```
data/game_data/
  extractions/<build-id>/
    manifest.json          the Build, and how it was extracted
    raw.sqlite             every image's tree, losslessly
    catalogue.sqlite       the typed layer, built from raw.sqlite
  images/<hh>/<name>.png   every canvas's pixels, shared by all extractions
  reports/<old>__<new>.html  the patch reports (#266)
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
item, read from `raw.sqlite` and nothing else. Code reads it through
`Catalogue` ("Looking things up"); anyone may query it directly with any
SQLite tool. Its tables and columns are stable within a schema version, the
`catalogue_schema_version` in the manifest (and the file's `user_version`).
Changing them bumps the version. A test holds this list and the schema
together.

Everything is in **virtual coordinates**, the map's own. An ID is an integer,
so the client's `000000100` is `100`. Booleans are 0 or 1. A flag the client
leaves out, such as `town` or a spawn's `f`, is 0. Where a column says NULL,
the client has no value there.

Where it comes from: `String/Map.img`, `String/Mob.img` and `String/Npc.img`
for `strings`; each `Map/Map/Map<n>/<id>.img`, and the `Map/Obj`, `Map/Tile`
and `Map/Back` images it draws from, for the map tables; `Map/Physics.img` for
`physics`. A client without one of these leaves its tables empty. One that is
there but isn't as expected stops the build, naming the image and the node,
and the extraction with it.

#### `strings`

| column        | type    | what                                               |
| ------------- | ------- | -------------------------------------------------- |
| `kind`        | TEXT    | `map`, `mob` or `npc`                              |
| `id`          | INTEGER | the map's, mob's or NPC's ID                       |
| `name`        | TEXT    | its name; a map's is `mapName`, without its street |
| `description` | TEXT    | a map's `mapDesc`; NULL otherwise                  |

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

### `images/`

Every canvas's pixels, as an RGBA PNG at `images/<first two hex>/<name>.png`.
The name is the client's `_hash` when the canvas carries one (mob and skill
frames do). Otherwise it's the SHA-256 of the decoded RGBA pixels, preceded by
the width and height. An image is decoded and written once, and is never
rewritten: a new extraction adds only the images that are new.
