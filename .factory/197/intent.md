---
ticket: 197
stage: plan
accepted_by: nassim
accepted_at: 2026-10-17
---

# Intent: let agents decide

## Problem statement

The #194 session produced nothing. No branch, no artifacts, no PR — it spent
itself asking questions the maintainer could not answer.

Nassim: *"The session on issue #194 is asking me tons of questions which I have
no clue what to respond; that's a big problem, and I have a sense this will keep
going on for every single ticket."*

The cause is in `docs/factory/`, not in the agent. `stages.md` has twelve "Stop
and hand back" sections and no counterpart. `roles.md` lists "resolving
escalations" as the human's job without defining an escalation. A careful agent
reading that treats every uncertainty as one, which is the correct reading of
what is written.

## Proposed outcome

An agent that cannot find an answer in the repo decides, records the decision
and its reasoning, and continues. Only three kinds of question reach the
maintainer, and they reach him batched in a PR rather than live.

## Affected users and systems

- Every ticket worked from now on.
- The maintainer, whose stated bottleneck is his own input and who is currently
  the destination for every uncertainty in the system.
- #180, which reviews specs: a spec that fails to say what the agent may decide
  is as incomplete as one with vague criteria.

## Constraints

- **Do not weaken the real stops.** A measured constant, a running client, a
  hard-stop path: those still stop. The change is to everything that is not one
  of those.
- The three things that need a human are already written in `roles.md`. This
  does not invent a rule; it makes an existing one operative.

## Open questions

- Should "Decide and record" be a slot in every stage section, or one rule
  stated once and referenced? Twelve copies would drift.
