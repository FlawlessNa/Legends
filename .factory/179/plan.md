---
ticket: 179
stage: build
radius:
  - docs/factory/**
  - AGENTS.md
  - .factory/179/**
tasks: null
merge_order: null
proof:
  red_test: null
  red_output_sha: null
  suite: pass
docs_cleared: null
---

# Plan

## Files that change

- `docs/factory/README.md` — entry point, the stage table, the enforcement markers
- `docs/factory/stages.md` — the ten stages, each with its gate
- `docs/factory/roles.md` — roles, write scopes, and the rule that generates them
- `docs/factory/artifacts.md` — the chain and the front-matter contract
- `docs/factory/bootstrap.md` — how to work a ticket before the tooling exists
- `AGENTS.md` — the always-loaded pointer, inserted before Orientation

## Order

README first, since the others are read through it; bootstrap next, because it
is the page a fresh agent needs most; artifacts before roles and stages, because
it is the contract #139 implements and the one with the least room for drift.
`AGENTS.md` last, so the pointer is never ahead of the thing it points at.

## Risks

- **Duplication.** Restating `AGENTS.md`, `CONTEXT.md` or an ADR is how
  documents drift apart. Mitigated by a "What this does not restate" section
  and by referencing rather than copying.
- **Describing the process as more real than it is.** Mitigated by requiring an
  enforcement marker on every rule, so an unbuilt gate reads as unbuilt.
- **Going stale.** This documentation is itself subject to epic #188.

## Proof of completion

No behaviour change and no new test: this is documentation. `method: assent`,
so completion is Nassim agreeing the documents say what the process is. The
suite must pass unchanged, which demonstrates only that nothing was broken.

This ticket is also the worked example its own `artifacts.md` demands, and
therefore discharges #148 — the schema is tested by being used.
