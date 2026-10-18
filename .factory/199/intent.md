---
ticket: 199
stage: plan
accepted_by: nassim
accepted_at: 2026-10-17
---

# Intent: the hooks never run

## Problem statement

The enforcement shipped in #189 does not execute. Observed live in the #194
worker's pane:

    Stop hook error: Failed with non-blocking status code:
    /usr/bin/bash: line 1: factory: command not found

`.claude/settings.json` registers `factory hook <event>`. `factory` is a console
script in `.venv`, and the hook's shell has no venv on `PATH`, so every call
exits 127. The failure is non-blocking, so **nothing is enforced and nothing
says so**.

Every ticket worked since #189 merged believed it was gated and was not.

## Proposed outcome

The hooks run. A hook that cannot run is loud rather than silent.

## Affected users and systems

- Every session on a ticket branch since #189 merged.
- #149, #150 and #194, which were to replace these hook bodies with calls to
  `factory gate` — they inherit the invocation, so fixing it here fixes them.
- The credibility of every PR body claiming a gate was mechanical.

## Constraints

- The fix must be proven from a **minimal-PATH shell**, the way the harness runs
  hooks. A developer shell with the venv active proves nothing.
- Do not make the hooks blocking-on-error without thinking: a hook that hard
  fails on a broken install locks the repo. Loud is the requirement; fatal is a
  separate decision.

## Open questions

- Should `SessionStart` verify the toolchain once per session, so a dead
  `factory` is reported before any work starts rather than at the end?
