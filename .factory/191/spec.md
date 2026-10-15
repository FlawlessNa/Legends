---
ticket: 191
stage: design
method: assent
criteria:
  - No CLAUDE.md exists anywhere in the tree, including the package shims
  - Any content from the deleted files that was not about the shim arrangement survives in AGENTS.md
  - The v2.1.277 version floor is documented where a human setting up the repo will see it
  - Verified in a real session that AGENTS.md loads natively, by the session's own startup line rather than by inspection
  - factory/CLAUDE.md is removed from the #137 branch so merging it cannot reintroduce the problem
specified_by: claude
specified_at: 2026-10-15
reviewed_by: null
---

# Spec: retire the CLAUDE.md shims

## Source

Issue #191. Nassim asked for this directly; the acceptance criteria below are
mine and carry the usual caveat.

## Requirements

1. Delete `CLAUDE.md`, `botting/CLAUDE.md`, `maple/CLAUDE.md`,
   `tests/CLAUDE.md` in one change.
2. The root file's content is entirely a description of the shim arrangement,
   so it is deleted rather than moved. Replace it with one line in `AGENTS.md`
   saying where Claude-specific guidance would go if any were needed.
3. Document the version floor in `docs/SETUP.md`, beside the other tooling
   requirements, because the person who needs it is a human setting up -- an
   agent on a too-old client cannot read a warning in a file it is not loading.

## Verification method: assent

The decisive check cannot be made from inside this session, which started with
`CLAUDE.md` present. A **new** session must print its startup line naming
`AGENTS.md`. Until someone sees that, this ticket is not done, and the PR says
so rather than claiming otherwise.

## Known gap in this spec

`specified_by` and the Builder are the same agent (#180).
