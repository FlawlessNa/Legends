---
ticket: 214
stage: design
cycle: 3
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "the folds this spec decides are applied as decided, so a review is current only when its stamped commit is the commit that wrote the current proof.md, §13's B3 row reads taken and its X1 row reads changed, and §4 gains a seventh rule"
---

# Spec review, cycle 3: commit the agreed factory design

**Verdict: `pass`.** This cycle checks only the four findings from
`spec-review-2.md`, against `spec.md` at `cc64a6f` (`git diff 37edddb cc64a6f`)
and #218's body on GitHub. All four are resolved. No finding remains open.

## 1. Review staleness: resolved

Criterion 10 and "Decided here" now say: "a review is current only when its
stamped commit is the commit that wrote the current `proof.md`". That is the
identity rule I proposed. A `plan.md`-only turn, such as a fixed red test,
`docs_cleared` or *Could not verify*, now produces a new proof and a stale
review. The Reviewer is dispatched again, and d1 does not come back.

#218's review row states the same rule. Its termination test now covers the
`plan.md`-only case ("Also with a Builder turn that changes only `plan.md`").
So the design and the ticket agree, which is what criterion 13's precedence
rule requires.

A note, not a finding. "Any Builder turn makes the review stale" slightly
overclaims. A turn that changes nothing, and a turn that fails judgement,
produce no new `proof.md` commit, so the review stays current. That is the
correct behaviour, because the cap then parks the ticket. `design.md` may
phrase it as "any Builder turn that is proven".

## 2. X1's order against GitHub: resolved

"Decided here" now says §10 follows GitHub, and drops X1's linear order on
purpose. I checked the two examples it names against the blocked-by links:

- #139 is blocked only by #214, so it can start before #216.
- #221 is blocked only by #207, so it can start before #218.

The fold table and criterion 10 both require §13's X1 row to read "changed".

## 3. §4 rule 7: resolved

The seventh rule is now stated in "Decided here": the loop's git never runs
code a worker could have written, meaning `core.hooksPath` empty,
`core.fsmonitor=false`, and pre-commit run as part of judgement. It is
appended after the source's six rules, so the citations of rules 2 to 5 keep
their numbers. Criterion 2's "source's order" still holds, and criterion 10
requires the rule.

## 4. Fold-table gaps: resolved

- X6 now includes §5 `state.py`.
- h now includes §9 `run`.
- X3 names §6 `proof.md`.
- X8 names §6 `plan.md` (`red_test`, `none`) and `proof.md` (`red`).

## What this review could not verify

These carry over from cycle 2:
- that the re-check text in the spec is verbatim;
- that the `.lavish` source is the final version;
- the suite figures the spec cites (1170 passed in 58 s).

I did not run pytest.
