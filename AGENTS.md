# Legends — agent instructions

Canonical instructions for any AI coding agent working in this repo, read
directly by Claude Code and by other agents alike. There are no `CLAUDE.md`
files: each package carries its own `AGENTS.md`, loaded when a file in that
directory is opened.

Keep guidance tool-neutral and put it here. If something is ever genuinely
specific to one tool, `.claude/AGENTS.md` is read too — but nothing needs that
today, and a rule that only one agent follows is a rule the others will break.

Claude Code reads `AGENTS.md` natively from **v2.1.277**. On an older client
these files load silently as nothing; see `docs/SETUP.md`.

## Are you working a ticket?

**If you are on an `issue/<n>-*` branch, you are working a ticket in the
factory.** Read `docs/factory/README.md` before you touch anything, and
`docs/factory/bootstrap.md` before your first ticket.

The short version, which is not a substitute for reading it:

1. `.factory/<n>/intent.md` and `spec.md` are **committed before any source
   change**, as the first commit on the branch.
2. `plan.md` names the radius — the only paths you may touch — before you touch
   them.
3. A behaviour change lands with a test that was **red without it**, proven by
   stashing the change and running it.
4. You open the PR. **You never merge.**
5. The PR body says what you could not verify, and which gates you checked by
   hand rather than mechanically.

Most of this is enforced by instruction rather than by a tool today. That is a
reason to be more careful, not less: the gates that would have caught you do
not exist yet, so the only thing standing between a wrong claim and a merged
one is what you write in the PR body.

If you are not on a ticket branch, the rest of this file is what applies.

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

## Where you may write

**Source edits in the primary checkout are refused.** [mechanical]

The primary checkout is the one whose `.git` is a directory — normally
`dev`-or-trunk, the clone you opened. All work happens on an `issue/<n>-*`
branch in **its own worktree**, so a direct source edit in the primary checkout
is always wrong, whatever branch it is on. The gate does not care which branch
that is, which is also why it cannot be talked past.

Writable there: `configs/`, `profiles/`, `toolkit/`, `docs/`, `.factory/`,
`AGENTS.md`, and `.claude/settings.local.json` — but **not** `configs/maps/`,
which is a hard-stop path.

To start work:

```
git worktree add ../<slug> -b issue/<n>-<slug>
```

and write `intent.md` and `spec.md` **in the new worktree**: `git worktree add`
carries no uncommitted changes, so artifacts written in the primary checkout
stay behind and the new worktree starts with an empty chain.

The gate only sees file-editing tools. A write through the shell is
**[unenforced]** — see #207. And `FACTORY_HOOKS=off` in
`.claude/settings.local.json` disables every gate on this machine; it is a
floor, not a lock.

## Verifying your work

```
pytest        ->  0 failed, 0 errors, 0 xfailed
```

That is the green baseline, from the repo root, no flags. **Any `failed` or
`error` line is yours.** Neither the passing nor the deselected count is pinned
here — both move every time anyone adds a test. What must hold is the shape:
nothing failed, no xfails, and every deselected test accounted for by an opt-in
marker (`live`, `system`, `lab`). `docs/agents/testing.md` explains why an
`XPASS` is a failure, and what each marker is for.

**A red `lab` test is not a broken build.** `lab` tests measure rather than
gate: a reading of real-world timing, or a measurement of a catalogued invariant
that does not hold yet. They are excluded from the default run on purpose. Read
them with `pytest -m lab`, and do not mark something `lab` to make it stop
failing — that is what `docs/planning/movement-invariant-catalogue.md` and a
ticket are for.

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
