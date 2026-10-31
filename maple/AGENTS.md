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

## Calibration

`maple/calibration/` is the closed-loop **Trial** framework (`CONTEXT.md` ->
Movement calibration). It knows nothing about DecisionMakers or clients, and is
checked offline: specs, records, and `TrialDriver`, which is fed a position and a
clock and answers. The bot around it is `CalibrationBot` + the `TrialRunner`
DecisionMaker, which holds the plumbing and no judgement — put new logic on the
driver's side of that seam.

Two boundaries hold:

- A **Trial record** (gitignored, `trial_records/`) is an experiment artifact.
  Session telemetry is the logging map's, and the two are joined on a cycle's
  Correlation ID, never merged.
- A Trial ships its Movement Plan through `controller.compile_and_send` like any
  other Action. A runner that compiled for itself would measure a copy of the
  system.

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

Game files are read by `game_data/` (top level, importing neither `maple` nor
`botting`), not by this package. See `docs/agents/game-data.md`.

## Parked code

Two files are parked, both for the same reason: they predate the MapleStory
Classic World (MSCW) client and have not been updated for it.

- `maple/model/interface/dynamic_components/inventory.py` reads the inventory
  with private-server pixel boxes and OCR. It needs an MSCW update before use,
  and says so in its module docstring. Its code is unchanged.
- `maple/decision_makers/inventory_manager.py`, below.

`maple/decision_makers/inventory_manager.py` is **parked**: it predates the JSON
minimap rewrite, still imports `maple._old.maps` and
`maple.model.mechanics.MinimapConnection` — both gone — and therefore raises on
import. It is disconnected at the import boundary (commented-out lines in
`decision_makers/__init__.py`), so nothing executes it and it never reaches test
collection.

Leave it parked. Don't delete it, don't comment out its body, and don't
re-enable the import as a drive-by — reconnecting it means porting its map
handling to the current model first. When lint and type gates land, exclude this
file explicitly rather than editing it into compliance.
