---
ticket: 216
stage: plan
accepted_by: nassim
accepted_at: 2026-10-22
---

# Intent: the gate that judges a worktree must not be loaded from it

## Problem statement

`.claude/hooks/factory-hook.sh` execs `python -m factory hook <event>`.
`python -m` puts the current directory first on the import path. The hook runs
in the session's directory, so a session in a ticket worktree imports **that
worktree's** `factory/` package.

A Builder on a factory ticket edits `factory/` as its job, so it is judged by
its own unfinished code. Picture an agent refused by a gate that "fixes" the
gate in its worktree. It has switched the gate off for itself, through the
error path rather than malice. The independent review demonstrated the
shadowing (`docs/factory/design.md` §3, d4; finding M3a).

## Proposed outcome

The hook always runs the gate code installed for the repository, which is the
primary checkout's `factory/`, whatever directory the session sits in. The
hook also takes the session's directory from the event the harness sends,
rather than assuming the process was started there.

## Affected users and systems

- `.claude/hooks/factory-hook.sh`.
- `factory/cli.py` (`_run_hook`).
- The hook tests.
- `factory/AGENTS.md`, which describes how the hooks run.

Every session in the repository, a human's included, runs these hooks.

## Constraints

- Hooks fail open. A hook that cannot find the factory must still say so, as
  it does today (#199). It must not fall silent.
- No decision a hook makes changes. Only *which code* makes it, and which
  directory it treats as the session.

## Open questions

Acceptance is inferred. The maintainer accepted the roadmap this ticket is part
of ("proceed, let's continue progress", 2026-10-22), and did not write this
issue's body. I wrote it, from the agreed design.
