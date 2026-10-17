---
ticket: 189
stage: plan
accepted_by: nassim
accepted_at: 2026-10-16
---

# Intent: make the factory refuse, not just ask

## Problem statement

Nothing refuses anything. `AGENTS.md` tells a session it is in the factory and
the entry skill routes it to a stage, but an agent that ignores both proceeds
exactly as if neither existed. Every gate in `docs/factory/` is currently
`[instruction]` or `[unenforced]`.

Nassim: *"nothing enforces you to follow the factory standards, not even
instructions-only... any fresh agent working on a ticket is likely to simply
skip everything."*

## Proposed outcome

Three hooks that stat the artifact chain and refuse. An agent on a ticket
branch cannot edit source before the chain exists, and cannot end its turn with
its proof block empty.

The observation that makes this worth building now rather than waiting for
`factory gate`: **enforcing the sequence is cheap; judging the quality of a
stage is expensive.** Checking that `spec.md` exists is a `stat`. Checking it is
any good needs #180.

## Affected users and systems

- Every session on an `issue/<n>-*` branch, Nassim's included. These are
  project settings hooks, the floor, not SDK role hooks.
- The `factory` package, which grows a `hook` subcommand.
- #149, #150 and #194, which replace these hook bodies with calls to
  `factory gate` rather than rewriting them.

## Constraints

- **A gate nobody can bypass in an emergency is a gate someone deletes.**
  `.claude/settings.local.json` is gitignored and is the per-machine override.
- Writing the artifacts must always be allowed, or the hook forbids the only
  action that would satisfy it.
- `PreToolUse` fires on every edit, so startup cost is a real budget, not a
  detail.

## Open questions

- Does the latency budget hold with a plain Python process per call, or does
  the `SessionStart` cache become necessary? Measured, not guessed.
