---
ticket: 189
verdict: changes-requested
reviewed_by: explore-subagent (read-only, no write access)
reviewed_at: 2026-10-16
transcribed_by: claude
---

# Spec review: #189

Produced by a read-only review agent that could not edit anything, given only
`intent.md`, `spec.md` and stage 2 of `stages.md`, and explicitly told not to
read the implementation. Its output is transcribed below unaltered. It is **not**
an independent reviewer in the sense #163 will provide — it was spawned by the
Builder — but it had no stake in the implementation and no memory of writing
the spec.

## What it checked

Read `intent.md` and `spec.md` in full, plus stage 2 of `stages.md` (trigger,
entry gate, the work, the oracle, artifacts, stop-and-hand-back). Traced each of
the nine criteria back to a sentence in the intent, then checked each for a
decidable pass/fail and for fit with `method: suite`. Read no Python.

## Findings

1. **Criteria 2, 5 and 8 contradict each other.** Criterion 2 denies "a write
   outside `.factory/`"; criterion 8 requires the override be documented in
   `factory/AGENTS.md`, which is outside `.factory/`. The gate forbids writing
   the file documenting its own escape hatch — the exact failure the intent's
   constraint names. The intent says an agent cannot edit **source**; the spec
   widened that to all writes outside `.factory/`, sweeping in `docs/`, tests
   and settings. Fix: define the denied set as source paths, or an allowlist.
2. **Criterion 7 is not decidable, and the 150ms is invented.** It passes if
   someone measures 400ms and writes it down — no threshold assertion — yet
   reads as a gate. Names no metric, percentile, sample count or machine. The
   intent's own open question says the budget is to be "Measured, not guessed",
   so the spec answered an open question by assertion. **A number invented
   before any measurement does not belong in an acceptance criterion: it is a
   hypothesis, and as written it cannot fail.**
3. **Criterion 9 has no root in the intent.** `intent.md` never mentions review,
   `spec-review.md` or stage 2's gate. The spec calls it a scope addition agreed
   with Nassim, but the accepted artifact is `intent.md`, and stage 2's
   stop-and-hand-back lists "the intent and the spec do not match" as a reason
   to hand back. Fix: amend and re-accept `intent.md`, or move it to its own
   ticket.
4. **Criterion 3 leaves two terms undefined.** *Source changed* against what
   baseline — working tree, last commit, merge-base? And what makes a proof
   block filled — a heading, a non-empty body, a command plus output?
5. **Gap: nothing requires the hooks to be installed.** Presence of the three
   entries in the committed `.claude/settings.json` is trivially decidable and
   is the difference between built and wired.
6. **Gap: the seam for #149/#150/#194.** Nothing requires the hook body to be a
   thin wrapper over the decision function, so a conforming implementation could
   inline the logic and break that promise.
7. **Gap: the ordering layer is unverified.** "The review commit touches only
   `.factory/<n>/` and lands before any source commit" is load-bearing for the
   forgery argument and checkable by `git log`, yet no criterion covers it.
8. **`method: suite` is right for most, wrong for three.** Criteria 1–6 are pure
   functions of a branch name and a filesystem state. Criterion 7 is a
   measurement; 8 and 9 are documentation-presence checks.

## Criteria it judged sound

> "decision logic is unit-tested from a branch name plus a filesystem state,
> with no harness"

Decidable because both inputs are named and the exclusion is explicit: a
reviewer opens the test file and either sees tests that construct a branch
string and a filesystem state and call the decision function directly, or sees
tests that need the harness. There is no judgement call in between.

> "writes under `.factory/` are always allowed, so the chain can be created"

Decidable by a single assertion per path: allow or deny, with the clause after
"so" stating the reason rather than adding a second condition.

> "none of the three hooks fire on a non-ticket branch"

Decidable once "fire" is read as "emit a deny".
