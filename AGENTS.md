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
  `toolkit/` holds **standalone scripts**: nothing imports them, they are run
  directly, and they are held to the same gates as the rest of the tree.

Dependencies point one way: `maple` imports `botting`, never the reverse. There
are no exceptions — the last one (`botting/visuals/object_detection.py`) was
removed by #85.

Each of `botting/`, `maple/`, and `tests/` has its own `AGENTS.md` with the
rules that only apply inside it. Read the one for the package you're touching.

For the engine's runtime shape — which process owns what, and how a decision
becomes a keystroke — see `docs/agents/engine-architecture.md`.

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

## Verifying your work

```
pytest        ->  0 failed, 0 errors, 11 xfailed, 2 deselected
```

That is the green baseline, from the repo root, no flags. **Any `failed` or
`error` line is yours.** The passing count is deliberately not pinned here — it
moves every time anyone adds a test. What must hold is the shape: nothing failed,
the 11 xfails are the ones tracked in issue #89, and the 2 deselected are the
`system`-marked tests. `docs/agents/testing.md` explains all three, and why an
`XPASS` is also a failure.

**Green means the Invariants hold. It does not mean the bot works.** Nothing in
the default suite drives a game client, and no test is `live`-marked today — the
marker is reserved and unused. Whole behaviours here have no offline proof: that
the character reaches the platform, that a rotation looks right, that inputs land
before the animation ends.

So one thing is required of every change: **say what you could not verify.** If
your change could alter which keys reach the game, or when, name that explicitly
in your report or PR body. An unverifiable change is fine. An unverifiable change
reported as done is not.

### A test that would have failed

A change to behaviour lands with a test that **fails without it**. Not "write the
test first" — nobody can check the order from a diff. Demonstrate it: stash the
source change, keep the test, run it, and confirm it goes red for the reason you
expect. A test that passes without your change is not testing your change.

**Refactors are exempt, and inverted**: no new test, and the existing suite passes
untouched. If you had to edit a test to make a refactor pass, it was not a
refactor — say so, and say what behaviour moved.

`docs/agents/testing.md` has the procedure.

## When to stop and hand back

Stop and ask rather than finishing, whenever the work needs:

- A **measured constant** — anything timed, tuned, or read off a running client.
  These are Expectations (`CONTEXT.md`), and no amount of reasoning settles them.
- A **running game client**, whether to reproduce, to confirm, or to record.
- A **minimap trail**, recorded through the GUI editor in
  `maple/model/mechanics/minimap_creation/`.
- A judgment that reduces to **watching the character**.

Stopping at these is compliance, not failure. Report what you finished, what you
did not, and what the human needs to do — a half-finished ticket with a clear
handoff is worth more than a guess.

`docs/agents/triage-labels.md` defines the same boundary at ticket level: work
resting on an Expectation is `ready-for-human`, however well specified.

## What you may change

Freely, when tests cover it and no ADR governs it: tests, docs, telemetry Event
Types (additive only), and offline logic — compilation, pathfinding, config
parsing, logging.

**Not without asking**, because the tests will not catch you being wrong:

- The input send path, focus handling, and the Held-Keys Ledger (ADR 0002).
- The telemetry envelope and transport (ADR 0001) — other consumers are written
  against it.
- Anything an ADR decides. Contradicting one is allowed; doing it silently is
  not.
- Map JSON under `configs/maps/` and pinned dependency versions.
- `maple/decision_makers/inventory_manager.py`, which is parked — see
  `maple/AGENTS.md`.

## Handing work over

Work is handed to the next person — a reviewer, or whoever picks it up — through
the PR body. `.github/PULL_REQUEST_TEMPLATE.md` is the shape: what changed, the
test that was red without it, **what you could not verify**, the ADRs and
invariant ids the change bears on, and what a human still has to do.

Reviewing is a different job with different inputs, and reading this file again
is not one of them. See `docs/agents/code-review.md`.

## Issue tracker

Issues live in GitHub Issues on `FlawlessNa/Legends`, via the `gh` CLI. See
`docs/agents/issue-tracker.md`.

## Triage labels

Canonical label vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`, which also
defines what `ready-for-agent` requires — a ticket is agent-workable only when
its acceptance criteria can be settled offline.

## Tests

pytest-native, always: plain module-level `test_*` functions, `@pytest.fixture`
in place of `setUp`/`tearDown`, and bare `assert`. This holds for new test
modules and for any unittest-style test you touch. See `docs/agents/testing.md`
for the translation table, the two opt-in markers (`live`, `system`), the shared
fixtures, and how to convert a module without changing its behaviour.

## Typing

Pre-commit runs Ruff and Pyright on staged files only, gated at Pyright
`standard` for the whole tree and `strict` for the one directory currently on
the Strict List (`botting/controller/inputs/`). Touching a file surfaces every
existing violation in *that file* — fix them, don't suppress them, and don't
bulk-fix a file you didn't otherwise need to touch. Never add a
`pyrightconfig.json`; it silently overrides `pyproject.toml` and breaks
editor/hook parity. See `docs/agents/typing.md` for the ratchet mechanics, the
"strongly typed" definition, and how a directory joins the Strict List.
