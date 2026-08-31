# Legends — agent instructions

Canonical instructions for any AI coding agent working in this repo. Claude Code
reads this file through `CLAUDE.md`, which imports it; other agents read it
directly. Keep tool-neutral guidance here, not in the per-tool files.

## Orientation

- `botting/` — the generic engine: process orchestration, input control,
  logging, telemetry transport. Knows nothing about MapleStory.
- `maple/` — the game-specific layer built on that engine: movement,
  decision-making, minimap model, interface reading.
- `tests/` — the pytest suite.
- `configs/` — `.ini` settings, plus one JSON per map under `configs/maps/`.
- `docs/adr/` — architecture decisions. `docs/agents/` — the reference docs the
  sections below point at.
- `toolkit/`, `ml_training/` — supporting tools and model training.

Dependencies point one way: `maple` imports `botting`, never the reverse. The
single existing violation (`botting/visuals/object_detection.py` importing
`maple_ign_finder`) is a defect, not a precedent.

Each of `botting/`, `maple/`, and `tests/` has its own `AGENTS.md` with the
rules that only apply inside it. Read the one for the package you're touching.

## Read before you explore

- **`CONTEXT.md`** at the repo root — the domain glossary. Its terms are the
  project's vocabulary; when your output names a domain concept (issue title,
  test name, refactor proposal), use the term as defined there and avoid the
  synonyms each entry explicitly rejects. A concept missing from the glossary is
  a signal: either you're inventing language the project doesn't use, or there's
  a real gap worth noting.
- **`docs/adr/`** — read the ADRs touching the area you're about to work in. If
  your change contradicts one, say so explicitly rather than silently overriding
  it.

See `docs/agents/domain.md` for the full convention.

## Issue tracker

Issues live in GitHub Issues on `FlawlessNa/Legends`, via the `gh` CLI. See
`docs/agents/issue-tracker.md`.

## Triage labels

Canonical label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`) — identity mapping. See
`docs/agents/triage-labels.md`.

## Tests

pytest-native, always: plain module-level `test_*` functions, `@pytest.fixture`
in place of `setUp`/`tearDown`, and bare `assert`. This holds for new test
modules and for any unittest-style test you touch. See `docs/agents/testing.md`
for the translation table, the `live` marker, the shared fixtures, and how to
convert a module without changing its behaviour.
