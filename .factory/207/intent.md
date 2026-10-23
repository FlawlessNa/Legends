---
ticket: 207
stage: plan
accepted_by: nassim
accepted_at: 2026-10-22
---

# Intent: the Stop gate judges what this session did, all of it, and nothing else

## Problem statement

Three defects in today's Stop gate, all reproduced by the reviews
(`docs/factory/design.md` §3, d3, and the first review's B3):

1. **Committing skips it.** `_source_changed` reads `git status --porcelain`, so
   source committed before stopping is invisible and no proof is owed.
2. **Shell writes are seen only while uncommitted.** `PreToolUse` sees edit
   tools alone, and Stop sees shell writes only until they are committed.
3. **A session is refused because of another ticket.** `_stop_everywhere`
   judges every ticket worktree, so a session with nothing wrong is blocked
   while any other ticket is mid-build. That makes any parallel work impossible
   without switching the hooks off.

The issue's original question (three options for shell writes) is settled by
the design: the factory loop's judgement of each turn is binding, and the hooks
are early warning. The loop does not exist yet, and every ticket is worked by
hand until it does, so the Stop gate must catch what it can until then.

## Proposed outcome

A session on a ticket is judged on its own worktree, over everything changed
since that worktree's base, committed or not. A session on no ticket is judged
on the ticket worktrees it actually wrote into. That keeps #206's guarantee
without the everyone-blocks-everyone failure.

## Affected users and systems

- `factory/cli.py` (the Stop wiring, `_source_changed`, and the write log in the
  pre-tool-use hook).
- Possibly `factory/hooks.py`.
- The Stop tests.
- `docs/factory/stages.md`.

## Constraints

- Hooks run on every edit: the write log must be a cheap append, never a
  subprocess.
- No branch name may be hard-coded (#217).

## Open questions

Acceptance is inferred. The maintainer accepted the roadmap and asked for work
to continue (2026-10-22).
