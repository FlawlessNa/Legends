---
ticket: 140
stage: design
method: suite
criteria:
  - factory next <ticket> computes the stage from the artifact chain alone, with no network and no clock
  - the answer names the stage, the role, the stages.md section, the commands to run, and the first missing artifact field
  - --json and a human-readable default, both from one payload
  - the stub table's row order is implemented exactly, first match wins, and a test asserts the order by exercising a chain that matches two rows
  - a chain with a gap in the middle routes to the earliest unsatisfied stage, not the latest present artifact
  - exit code 3 when the chain says stop and hand back, 0 otherwise
  - review.md and qa.md gain a contracted verdict field, documented in artifacts.md, so no verdict is read by eye
  - the stub section is deleted from SKILL.md, not left beside the real thing
  - a non-ticket branch is not an error, it reports that no ticket applies
specified_by: claude
specified_at: 2026-10-18
reviewed_by: see spec-review.md
---

# Spec: `factory next`

## Source

Issue #140. Its body predates #153 and shows a per-stage skill path
(`.claude/skills/factory-test`) from a design that was replaced; the `skill`
field names a `stages.md` section instead. Recorded in `intent.md` as stale
rather than silently followed.

## The routing table is the specification

`.claude/skills/factory/SKILL.md`'s stub holds ten ordered rows. They are the
contract, not a sketch: **first matching row wins**, and the stub says in as
many words that a later row must not be preferred because it looks closer to
where someone thinks the ticket is. A chain with a gap in the middle therefore
routes backwards, to the earliest unsatisfied stage.

## What the stub could not do, and this must

1. **Verdicts have no contracted field.** `review.md` and `qa.md` are read by
   eye today. Both gain `verdict`, documented in `artifacts.md`.
2. **No exit code.** Row 6 — a failed review, or a failed QA — must exit 3, not
   rely on a human noticing a Stop slot.

## Verification method: suite

A pure function of a filesystem state. Every row is a test; the ordering is a
test; the gap case is a test.

## Known gap

`specified_by` is the Builder (#180).
