---
ticket: 206
stage: plan
accepted_by: nassim
accepted_at: 2026-10-18
---

# Intent: the gate must look at the file, not at the session

## Problem statement

`decide_write` asks `ticket_from_branch(branch)`, where `branch` is the branch
of the **session's** working directory. If that is not a ticket branch it
returns `INDIFFERENT`, and every write is allowed — including a write into a
ticket worktree that is squarely under the factory.

That is how every factory ticket to date was actually built: the session sits in
the main checkout on `movements-improvements`, and the ticket's worktree is
edited by absolute path. **The gates were never once consulted.** The artifacts
did land before the code, and the spec reviews did happen, but by discipline —
which is the single thing this project exists to stop relying on.

There are two holes, not one:

1. **The target path is never compared to anything.** `decide_write` ignores
   where the file it is judging actually lives.
2. **The chain is read from the wrong worktree.** Even on a ticket branch,
   `read_chain(repo_root, ticket)` reads the session's `.factory/<n>/`, not the
   one belonging to the file's own worktree.

`decide_stop` has the same shape: `_source_changed` runs `git status` in
`repo_root`, so source changed in another worktree is invisible and the proof
gate passes vacuously.

## Proposed outcome

The decision is a function of **the file being written**. Walk up from the
target to its own worktree root, read that worktree's branch, and judge against
that worktree's chain. The hook then gives the same answer wherever the session
happens to sit, which is the property it was supposed to have all along.

## Affected users and systems

- Every gate in `factory/hooks.py`, and therefore every ticket.
- #163, which cannot be correct before this is: a per-role write scope resolved
  from the session's branch would be enforced against the wrong chain.
- Anyone working the way I have been — the gates will start firing, and that is
  the point.

## Constraints

- **Still no subprocess in `PreToolUse`.** It fires on every edit, so the
  worktree must be found by reading files, the way `current_branch` already
  reads `HEAD` rather than running git.
- **Pure.** A function of a path and a filesystem state.
- Must not refuse the write that would satisfy the gate, which is the deadlock
  review caught in #189.

## Open questions

- **Where the factory's jurisdiction ends.** The ticket body I filed says "an
  unresolvable target must fail closed". Taken literally that refuses every
  write to a scratchpad or temp file, which is both noisy and none of the
  factory's business. The honest line is narrower and `spec.md` draws it: fail
  closed only where the factory has jurisdiction, which is inside a ticket
  worktree.
- Whether to *also* refuse cross-worktree writes outright. Resolving from the
  target makes refusing unnecessary, and banning a workflow is weaker than
  enforcing the right rule on it.
