---
ticket: 202
stage: plan
accepted_by: nassim
accepted_at: 2026-10-18
---

# Intent: corrections from the first live run

## Problem statement

Running the factory on itself for the first time surfaced three defects, none
of which review had caught:

1. `.claude/**` is auto-mergeable. The merge policy trusts the ticket's labels,
   an agent can relabel its own ticket, and the hooks that would stop it live in
   `.claude/`. A `type:chore` PR can disable the gates and merge itself.
2. `.factory/**` is not allowlisted, so no ticket PR can ever auto-merge. The
   feature cannot fire on the work it was built for.
3. The heartbeat only prints on ticket branches, so on the trunk a session sees
   nothing — indistinguishable from the hooks being dead, which is the exact
   failure #199 existed to make visible.

Nassim hit (3) directly: after merging #201 he saw no `factory gates: LIVE` and
could not tell whether the fix had worked.

## Proposed outcome

The enforcement cannot merge a change to itself; the policy can fire on factory
tickets; and every session can tell whether the gates are alive.

## Affected users and systems

- The merge policy (#194) and its allowlist.
- Every session, ticket branch or not.
- #163, whose per-role scopes are the real fix for the label-trust problem.

## Constraints

- Widening `allowed_paths` must never relax `hard_stop_paths`; they are checked
  independently and that must stay true.
- The heartbeat must not narrate at ordinary sessions. One line, then silence
  unless there is a ticket.

## Open questions

- The policy trusts labels, which an agent can set. Excluding `.claude/**`
  removes the worst consequence but not the cause. The cause is label trust,
  and only #163's write scopes fix it properly.
