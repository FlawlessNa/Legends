---
ticket: 209
stage: plan
accepted_by: nassim
accepted_at: 2026-10-18
---

# Intent: the one checkout where nothing governs anything

## Problem statement

#206 made a write judged by the worktree the file lives in. It closed the case
where a session sits outside the worktree it is editing, and left open the case
where **neither side is a ticket**: a session in the primary checkout, editing
the primary checkout. Verified after #208 merged:

    decide_write(<primary>/botting/controller/inputs/focus.py, session=<primary>)
    -> allowed = True

`botting/controller/inputs/` is on the hard-stop list and the one directory on
the Strict List. A session in the primary checkout can rewrite it with no
`intent.md`, no `spec.md`, no review, and no radius.

This is the orchestrator's own seat. Every factory ticket so far was driven
from it, which is the same observation #206 started from: the gates were not
enforcing, they were being remembered.

## Proposed outcome

In the primary checkout, source writes are refused. The settings a human edits
and the standalone tools they run are not.

Nothing needs to be *distinguished* to know this: `AGENTS.md` and
`bootstrap.md` already say all work happens on an `issue/<n>-*` branch in its
own worktree, so a direct source edit in the primary checkout is always wrong.
That is why this needs no role and no registration step — a step that can be
skipped is the failure mode being designed out.

## Affected users and systems

- Every agent, and the maintainer, who has accepted the friction provisionally.
- #163, whose per-role scopes sit on top of this floor rather than replacing it.
- Me, immediately: this is the gate that will refuse my own edits.

## Constraints

- **The anchor is structural, never a branch name.** An earlier draft keyed off
  "the working branch" and named `movements-improvements`. Nassim: *"it just
  happens to be the 'working branch' right now, but it could be `dev` or
  anything else."* The primary checkout is identifiable without configuration:
  its `.git` is a directory, a linked worktree's is a file pointing into
  `<primary>/.git/worktrees/<name>`.
- **No subprocess.** `PreToolUse` fires on every edit, so the rule cannot ask
  `git check-ignore` whether a path is tracked, however natural that reading is.
- **Revertible by one edit.** The maintainer is trying this for days or weeks.
  One constant, one call site. If reverting means unpicking three places it will
  not be reverted, it will be `FACTORY_HOOKS=off`-ed, which disables every other
  gate too.
- **Every agent must know before being refused.** Nassim: *"I don't want a
  random agent to 'have to figure this out on its own' (thereby wasting
  tokens)."* The rule has to be in context before the first edit, not
  discovered by being denied.

## Open questions

- **`configs/maps/**` is a hard-stop path.** Blanket-allowing `configs/**` makes
  map JSON freely editable here. `spec.md` decides: carve it out, or state that
  the hard-stop list is enforced at merge rather than at the write gate.
- **The refusal must name an action that exists.** `factory claim` (#147) is
  what should create the branch and worktree, and it is not built. Until it is,
  the reason has to give the concrete commands — a gate whose advice names a
  missing command is a gate people switch off.
