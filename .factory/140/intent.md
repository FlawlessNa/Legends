---
ticket: 140
stage: plan
accepted_by: nassim
accepted_at: 2026-10-18
---

# Intent: the command that removes the most randomness

## Problem statement

An agent on a ticket branch currently works out its own stage from a table in
`.claude/skills/factory/SKILL.md`, marked **STUB — replace with `factory next`
when #140 lands**. Reading a table is a judgement, and two agents reading the
same chain can reach different answers. That is precisely the randomness the
factory exists to remove.

The stub also cannot do two things it names itself: read a verdict from a
contracted field — `review.md` and `qa.md` have none, so a reviewer's verdict
is read by eye — and return an exit code rather than relying on a human to
notice a Stop slot.

## Proposed outcome

`factory next <ticket>` answers, from the chain alone: which stage, which role,
which section of `stages.md`, what to run, and what is missing. Two callers on
the same chain get the same answer because it is computed, not read.

## Affected users and systems

- Every agent working a ticket. This becomes its first action.
- `.claude/skills/factory/SKILL.md`, whose stub is **deleted**, not extended.
- #159, the Foreman: this is the one thing it cannot fake.
- `review.md` and `qa.md`, which gain contracted `verdict` fields.

## Constraints

- **Pure.** A function of the chain and nothing else — no network, no git
  beyond the branch, no clock. Two callers, same answer.
- The stub's row order is the specification. It was written deliberately: first
  matching row wins, and later rows must not be preferred because they look
  closer to where someone thinks the ticket is.
- Must honour the exit-code contract: 3 when a person is needed.

## Open questions

- #140's own body shows `"skill": ".claude/skills/factory-test"`, a per-stage
  skill path from a design #153 replaced. The field should name a `stages.md`
  section instead. Treating the body as stale rather than authoritative.
