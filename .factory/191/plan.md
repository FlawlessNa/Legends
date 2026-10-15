---
ticket: 191
stage: build
radius:
  - CLAUDE.md
  - botting/CLAUDE.md
  - maple/CLAUDE.md
  - tests/CLAUDE.md
  - AGENTS.md
  - CONTRIBUTING.md
  - docs/SETUP.md
  - .factory/191/**
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

Deleted: the four `CLAUDE.md` shims. The root file's content described only the
shim arrangement, so it goes with it rather than moving.

Updated: `AGENTS.md` (its opening said Claude reads it *through* `CLAUDE.md`,
which is now false), `CONTRIBUTING.md` (same claim, plus a pointer to
`docs/factory/`), `docs/SETUP.md` (the version floor).

## Order

All four deletions in one commit. A partial migration is worse than none: any
remaining `CLAUDE.md` at or above the working directory makes Claude ignore
every `AGENTS.md` in the tree.

## Risks

- **Silent failure on an old client.** Below v2.1.277 these files load as
  nothing and no message says so. Mitigated by documenting the floor in
  `docs/SETUP.md`, where a human setting up will see it -- not in `AGENTS.md`,
  which such a client is not reading.
- **Reintroduction by #137.** That branch adds `factory/CLAUDE.md`. Removed
  there in the same pass, so merge order cannot resurrect the problem.

## Proof of completion

No behaviour change, no new test: deletions and documentation. The suite must
pass unchanged.

The decisive check cannot be made from this session, which started with
`CLAUDE.md` present. A new session must print the startup line naming
`AGENTS.md`. Recorded under "Could not verify" rather than claimed.
