# `maple/` — the game layer

MapleStory-specific behaviour built on the `botting/` engine: movement,
decision-making, the minimap model, and interface reading.

## Speak the glossary

`CONTEXT.md` defines this layer's vocabulary, and the movement pipeline is the
part most often described in the wrong words. It runs
**Path → Movement Plan → Input Sequence → Step**, and "Action" is a fifth thing
— the request sent to Main Process, not the compiled keystrokes. Check the
glossary before naming something in a test, an issue, or a new attribute.

## Movement

Per ADR 0002, a movement Action carries the **Movement Plan** plus the inputs
needed to compile it. It never carries a compiled Input Sequence — compilation
happens at dispatch, inside the focus lock, in the engine layer. The compiled
`action` attribute remains only as the offline movement lab's artifact.

## Telemetry

Event Types are constants in `maple/telemetry_events.py`, and payloads are the
`TypedDict`s beside them:

- Pass a constant, never a literal.
- The taxonomy is **additive only** — new areas and events are added freely,
  existing ones are never removed or repurposed, because an offline analyzer is
  written against them.
- Payloads carry JSON primitives only, converted at the call site: `int()`
  around anything numpy produced, a `Box` decomposed into named fields.

## Maps and minimaps

The live path is **JSON, one file per map, under `configs/maps/`**, authored
with the GUI editor in `maple/model/mechanics/minimap_creation/`.

`maple/model/mechanics/game_file_extraction/` parses game files directly and is
the older approach; `map_parser.py` has no remaining importers and is slated for
removal. Don't build new features on it.

## Parked code

`maple/decision_makers/inventory_manager.py` is **parked**: it predates the JSON
minimap rewrite, still imports `maple._old.maps` and
`maple.model.mechanics.MinimapConnection` — both gone — and therefore raises on
import. It is disconnected at the import boundary (commented-out lines in
`decision_makers/__init__.py` and `bots/leeching.py`), so nothing executes it and
it never reaches test collection.

Leave it parked. Don't delete it, don't comment out its body, and don't
re-enable the import as a drive-by — reconnecting it means porting its map
handling to the current model first. When lint and type gates land, exclude this
file explicitly rather than editing it into compliance.
