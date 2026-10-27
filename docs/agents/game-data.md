# Game data

`game_data/` reads MapleStory Classic's client files on disk and extracts them
into a store, so the bot can look up maps, mobs and skills instead of having
them typed in by hand. It never touches the running game. The epic is #259;
its intent and spec are the issue body.

This page covers setting it up, the two commands, and the store's layout for
anyone reading it directly. Later tickets add the catalogue, the patch report
and the renderer.

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
```

`--root` is the store, `data/game_data` by default (gitignored, like all of
`data/`). Everything `game_data` writes goes under it.

- **`extract`** extracts the installed client into the store. After a patch,
  running it again is the whole update. It prints the build id, how many
  images and canvases it stored, how many new images it added, and the
  failures. Extracting the full client takes a long time: every canvas is
  decoded and written as a PNG.
- **`status`** prints `missing` (no extraction yet), `fresh` (the installed
  client is the latest extraction's Build) or `stale` (it isn't: run
  `extract`). It only `stat`s the archives, so it is quick enough for every
  bot startup. It reads an archive only when its size matches but its
  modification time doesn't, to tell a touched file from a changed one.

Both exit with 1 and a message on stderr when something goes wrong.

The same functions, for code: `game_data.extraction.extract(client, root)` and
`status(client, root)`. Every entry point takes the store root. **Tests and
`client_files` runs pass a temporary root, never the real store**, because
extracting deletes old extractions.

## The store

```
data/game_data/
  extractions/<build-id>/
    manifest.json          the Build, and how it was extracted
    raw.sqlite             every image's tree, losslessly
    catalogue.sqlite       the typed layer (#264)
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
| `catalogue_schema_version` | the catalogue's schema version, `null` until #264                 |
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

### `images/`

Every canvas's pixels, as an RGBA PNG at `images/<first two hex>/<name>.png`.
The name is the client's `_hash` when the canvas carries one (mob and skill
frames do). Otherwise it's the SHA-256 of the decoded RGBA pixels, preceded by
the width and height. An image is decoded and written once, and is never
rewritten: a new extraction adds only the images that are new.
