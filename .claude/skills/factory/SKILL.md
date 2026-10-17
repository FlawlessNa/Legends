---
name: factory
description: Route a factory ticket to its current stage. Use whenever you are on an issue/<n>-* branch, or are asked to work, continue or pick up a ticket in the Legends factory. Computes the stage from the .factory/<n>/ chain and points at the section of docs/factory/stages.md to follow; never choose a stage yourself.
---

# Factory: entry

This file routes. It holds no stage instructions — those live only in
`docs/factory/stages.md`. If this file and that one ever seem to disagree, this
file is wrong.

1. Run `factory next <ticket>`. It names the stage, the role and the section to
   read.
2. Read `docs/factory/stages.md` → "How to read a stage section", then the
   section it named. Follow that section.
3. Do not choose a stage yourself, and do not proceed past a non-zero exit code.
4. When the section's oracle holds and its artifacts are committed, start again
   at step 1.

## Stub: until `factory next` exists

> **STUB — replace with `factory next` when #140 lands. Do not extend it.**
> Today `factory next` is not implemented, so step 1 is this table instead.

`<n>` is the number in the branch name `issue/<n>-<slug>`. Read the front-matter
of each file in `.factory/<n>/`, then take the **first** row whose condition
holds. Do not skip a row because a later one looks closer to where you think the
ticket is.

| # | Condition on the chain | Stage | Role | Section of `stages.md` |
| --- | --- | --- | --- | --- |
| 0 | Branch is not `issue/<n>-*` | — | — | None: not a factory ticket. `AGENTS.md` applies |
| 1 | `intent.md` missing, or `accepted_by: null` | `plan` | Clerk | 1 · Plan |
| 2 | `spec.md` missing, or `spec-review.md` missing | `design` | Specifier / Specification Reviewer | 2 · Design |
| 3 | `plan.md` missing | `build-planning` | Builder | 3 · Build, planning |
| 4 | `plan.md` → `proof.suite: null` | `build-implementing`, then `test` | Builder | 4 · Build, implementing; then 5 · Test |
| 5 | `review.md` missing | `review` | Reviewer | 6 · Review |
| 6 | `review.md` records anything but a pass, or `qa.md` exists and does | — | — | None: stop and hand back |
| 7 | `spec.md` → `method` is `live` or `both`, and `qa.md` missing | `qa` | QA Operator | 7 · QA |
| 8 | `plan.md` → `docs_cleared: null` | `document` | Documenter | 8 · Document |
| 9 | Otherwise | `integrate` | Integrator | 9 · Integrate |

Stage 10, Maintain, has no row: it is never reached from an existing ticket.

What the stub cannot do, and `factory next` must: read a verdict from a
contracted field — `review.md` and `qa.md` have none yet, so row 6 is read by
eye — and return exit code 3 rather than relying on you to read a Stop slot.
