---
ticket: 214
stage: plan
accepted_by: nassim
accepted_at: 2026-10-22
---

# Intent: put the agreed factory design where agents can read it

## Problem statement

The factory's design was agreed on 2026-10-22, in three review documents under
`.lavish/`: the lifecycle, the architecture, and two independent reviews. The
maintainer then accepted all eleven rulings at their defaults. `.lavish/` is
gitignored. Every ticket on the roadmap (#171) cites `docs/factory/design.md`,
and no agent working in a ticket worktree can read the design until it is in
the repo.

## Proposed outcome

`docs/factory/design.md` holds the agreed design as one document, with the
re-check's amendments folded into the sections they change rather than
appended. The four process documents it supersedes say so at the top, without
being rewritten. The factory's orchestrating program gets a name that does not
collide with the bot's own `Engine`, and "Foreman" is retired.

## Affected users and systems

- Every agent working a roadmap ticket, which reads `design.md`.
- `docs/factory/` and `CONTEXT.md`. No source, no tests and no configuration.

## Constraints

- No behaviour changes. The supersedes notes say what *will* change, and that
  each document stays true of today until its owning ticket lands.
- Every claim about current code must hold at the merge base (`4296edc`).

## Open questions

None. The maintainer accepted the design and asked for work to start.
Accepting this intent is that instruction ("Proceed", "get to work",
2026-10-22).
