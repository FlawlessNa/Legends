---
ticket: 140
verdict: changes-requested
reviewed_by: explore-subagent (read-only, no write access)
reviewed_at: 2026-10-18
transcribed_by: claude
---

# Spec review: #140

The spec declared the entry skill's ten-row stub "the specification". The review
walked those rows against real chains and found the table unsound in three ways.
It is the table that is wrong, not the implementation of it.

## 1. The router never terminates for a live-only ticket — ACTED ON

> "Row 4 is `plan.md → proof.suite: null` → `build-implementing, then test`... For
> a live-only ticket there is no suite proof to record, so `proof.suite` stays
> `null` legitimately, row 4 matches on every invocation, and rows 5-9 are
> unreachable: the ticket can never reach review, QA, document or integrate."

A routing function with no fixed point. Fixed by adding a **termination test**
that drives a fully-populated chain to `integrate` for every legal `method`
value, so an unreachable terminal row fails the suite rather than wedging a
ticket.

## 2. A failed review is an absorbing state — ACTED ON

> "Nothing in the table routes a failed review back to the Builder, so 'stop and
> hand back' means the ticket is wedged at exit 3 until a human edits or deletes
> an artifact out of band. The one case where going back to build is the
> *correct* answer is the one case the table refuses to do it."

Correct, and it would have made every rejected review a manual rescue. The
verdict domain now distinguishes the two cases: `changes-requested` routes back
to `build-implementing`, `fail` stops.

## 3. A late amendment destroys downstream work — ACTED ON, differently

> "A ticket at QA whose `spec-review.md` was never committed, or whose
> `intent.md` was reopened for amendment, routes to `plan`/`design` — and the
> Clerk/Specifier sections rewrite `intent.md`/`spec.md`, invalidating the
> already-reviewed `plan.md`, `review.md` and the implementation."

The review suggested gating rows 1-2 on no downstream artifact existing. Taken
one step further: a chain with a **hole upstream and work downstream is an
inconsistent state**, not a stage to re-run. It now blocks with exit 3 and names
the hole, rather than silently sending a finished ticket back to the Clerk.
Redoing is more destructive than stopping.

## 6. The verdict domain was undefined — ACTED ON

> "'anything but a pass' is *not* well-defined once `verdict` exists... an
> incomplete review reads as a failed review and wedges the ticket at exit 3
> instead of routing to `review`."

Exactly right, and my first implementation had this bug. `artifacts.md` now
enumerates `pass | changes-requested | fail`; a **missing or null** verdict is an
incomplete artifact that routes to that stage's own row, and an **unrecognised**
value is a hard error rather than being guessed either way.

## Findings not acted on

- **4 — criterion 5 is redundant with criterion 4.** Correct; it restates
  first-match-wins and is undecidable for the two stage-less rows.
- **5 — the exit-code mapping is narrower than the intent's constraint.** Row 1's
  `accepted_by: null` also needs a person and would exit 0. True. Left as-is
  because an agent reaching stage Plan has work to do (drafting the intent for
  acceptance), so 0 is right; the intent's phrasing is what is loose.
- **7 — criterion 1 drops the intent's "no git" clause**, and `--json` traces to
  no intent line. Both correct; both Specifier fixes.

These four are spec wording. The Builder does not rewrite criteria it finds
inconvenient, so they are recorded.
