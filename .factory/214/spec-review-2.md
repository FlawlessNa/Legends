---
ticket: 214
stage: design
cycle: 2
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "the two folds this spec decides are applied as decided, so review staleness compares source between review.commit and proof.commit, and §13's B3 row reads taken"
---

# Spec review, cycle 2: commit the agreed factory design

**Verdict: `changes-requested`, narrowly.** The revision takes all 13 findings
seriously, and 11 of them are fully resolved. The blocking problem left is one
the revision introduced. Criterion 10 requires a review-staleness rule that
rebuilds d1, the endless review loop, for exactly the fixes a Reviewer is told
to ask for. #218's body now carries the same rule. The remaining findings are
small edits to the fold table and to "Decided here".

I read the revised `spec.md` at `37edddb`, the source's §4 and §6 again, #218's
updated body, and the blocked-by links of the Phase 0 and Phase 1 tickets. I ran
no tests.

## Cycle 1, finding by finding

| # | Cycle-1 finding | Now |
| --- | --- | --- |
| 1 | Re-check in no file | **Resolved.** The re-check is in the spec as delivered, with a fold table. The table has gaps (findings 3 and 4 below) |
| 2 | Foreman criteria contradict | **Resolved** by criterion 14's carve-out. `models.py` and the toml are named out of scope, with #218 as owner |
| 3 | Two folds contradict the design | **B3 resolved. Staleness decided wrongly** (finding 1 below) |
| 4 | X1 against GitHub for P6 | **Agreed on P6**, but the same gap exists for all of X1's ordering (finding 2 below) |
| 5 | Ticket bodies go past the source | **Resolved.** The precedence rule and the three known cases are good |
| 6 | Anchors lost | **Resolved** by criterion 2. Its effect on a new §4 rule is in finding 3 below |
| 7 | No status line | **Resolved** by criterion 3, plus the README entry in criterion 15 |
| 8 | Non-code claims | **Resolved** by criterion 9 |
| 9 | §11 against #171 | **Resolved** by criterion 8 |
| 10 | Supersedes note vague | **Resolved** by criterion 14. The not-renumbering reason is kept in Not in scope |
| 11 | Engine criterion | **Resolved** by criterion 11, which is now a grep plus `factory/loop.py` |
| 12 | Scope too wide; wrong test | **Resolved** by criteria 16 and 17 and the corrected test citation |
| 13 | §2 diagram | **Resolved**: a text diagram, then the stage table |

The naming changes are right as revised:
- a `## The factory` section;
- an Orchestrator entry, crediting #211's use of Foreman;
- `_Avoid_` lines that give their reasons;
- a preamble that scopes session, attempt, snapshot and run;
- bare "the loop" allowed inside `docs/factory/` only.

## 1. The decided staleness rule makes the Reviewer's own requests unanswerable (blocking)

"Decided here" says a review is current "when no source differs between
`review.commit` and `proof.commit`, ignoring `.factory/`". Criterion 10 makes
that binding.

Ignoring `.factory/` is right for proofs, since a proof is about source (B2).
It is wrong for reviews, because the design gives the Reviewer three duties
that live **inside** `.factory/`, all in `plan.md`:

- **The red test.** §7: "A weak `red_test` passes. **The Reviewer judges it.**"
- **`docs_cleared`.** R9: "The Builder fills `docs_cleared`, and the Reviewer
  judges it with the rest."
- **Could not verify.** M9, §6: `plan.md` carries the required section.

Walk the case. The Reviewer returns `changes-requested`: "the red test does not
test the change". The Builder's turn edits `plan.md`'s `red_test` and nothing
else. The loop judges the turn, commits it, and proves it again: a new
`proof.md` with a new `red_test`. Under the decided rule, no source differs
between the old `review.commit` and the new `proof.commit`, so the old review
is still **current**. It still says `changes-requested`, so routing sends the
ticket back to the Builder, and the Reviewer is never dispatched to see the
fix. The cycle counter climbs until the cap parks the ticket.

This is exactly the probe that reproduced d1 in `review.html`: "rewriting
plan.md with a new red_test and commit … before: build-implementing, after
fresh proof: build-implementing". The cap now turns the endless loop into a
park, but the defect is the same. #218's new acceptance test ("changes-requested
→ new proof → stale review") only exercises the case where the source changes,
so it would not catch this.

**Fix.** Bind the review to the proof it judged, by identity:

> A review is current when its loop-stamped `commit` is the commit that wrote
> the current `proof.md`.

That commit is exactly c's snapshot. The loop proves every Builder turn
(#145), so any Builder turn that changes anything, `plan.md` included, writes a
new `proof.md`, and the old review goes stale. A Builder turn that changes
nothing leaves `proof.md` byte-identical: there is no new commit, the review
stays current, and the cap parks the ticket. That is the right outcome.

A second option, if the specifier prefers a diff: ignore only the files that
the loop and the judges write (`proof.md`, `review.md`, `spec-review.md`,
`acceptance.md`, `run.md`), not all of `.factory/`.

Either way, update criterion 10, "Decided here", and #218's review row and its
termination test. #218 is a GitHub change, and it is the coordinator's to make.

## 2. P6 is right, but X1's whole order differs from GitHub, not only P6

I accept the specifier's argument on P6. The verbatim X1 says "P6 needs the
`proof.md` schema (S4)", and nothing from routing. The summary I was handed in
cycle 1 ("P4, P5 and P6 depend on S4 and S5") overstated it.

But X1's **fix** is a linear order: "S1–S3, then P1 and P2, then S4, then S5
… then P3–P6". GitHub's graph is looser in three places:

- **#139 (S4)** is blocked by #214 only, so it can start before S1.
- **#221 (P3)** is blocked by #207 only, so it can start before S5.
- **#145 (P6)** is not after S5, as "Decided here" already says.

Every **dependency** X1 names is in the graph:
- P4 reaches S4, S5 and P1;
- P5 reaches S4 and S5;
- P6 reaches S4;
- S5 reaches P1.

So the graph is X1 with its order relaxed, which is defensible. But criterion 7
puts the graph in §10, and criterion 9 says X1 "changes" §10. A reader checking
§13's X1 row against §10 will see a different order and no explanation.

**Fix.** Widen the P6 bullet in "Decided here": §10 follows GitHub's graph,
which keeps every dependency X1 names but not its linear order (S4 from the
start; P3 and P6 not after S5). §13's X1 row then reads "changed" rather than
"taken", using the design's own convention for "solved another way".

## 3. The fold table cites a §4 rule that does not exist

X6 is folded into "§4 rules 2, 5 and **7**", and f into "§4 rules 2 and **7**".
The source's §4 is "Six rules the architecture follows", with HTML ids `p1` to
`p6`. If a seventh rule is meant (presumably the loop's git hygiene: hooksPath
empty, fsmonitor off, pre-commit as judgement), the Builder has to invent its
wording and change the heading. Criterion 2 also pins §4 to "the source's
order", which a seventh rule stretches.

**Fix.** Either say what rule 7 states, and that it is appended so that the
cited rules 2 to 5 keep their numbers, with the heading becoming "Seven rules".
Or fold X6 and f into §5 `gitops.py` and §4 rule 2 instead.

## 4. Three smaller gaps in the fold table

- **X6 misses §5 `state.py`.** The source's `state.py` row lists `turn_base`
  among the `state.json` fields. X6 says `turn_base` in `state.json` is an
  unjudged write and must be kept in memory. Left as it is, §5 contradicts
  §4 rule 2.
- **h misses §9 `run`.** The re-exec on a change to the primary's HEAD is
  behaviour of the `run` command (§9; R2), not only of §7 and §8.
- **"§6 the red test"** (X3 and X8) names no §6 row. §6's rows are `plan.md`
  (`red_test`) and `proof.md` (`red`). Name them.

## What this review could not verify

- That the re-check text in the spec is verbatim. I was given a summary, and the
  spec's version is more detailed and consistent with it, but nothing else holds
  the original.
- That the `.lavish/factory-design.html` I read is the final version, as the
  spec now asserts.
- The suite count and time the spec cites (1170 passed in 58 s). I did not run
  pytest.
