# The stages

Each stage consumes the previous stage's artifact, produces its own, and refuses
to start until its gate passes. Enforcement markers are defined in
[README.md](README.md).

## 1 · Plan → `intent.md`

What is wanted, why, and under which constraints, in the originator's language
before any process touches it. Sections: problem statement, proposed outcome,
affected users and systems, constraints, open questions.

**Gate to leave:** accepted by the maintainer. This is not a peer review —
there is no ground truth for an intent except the originator. **[instruction]**

## 2 · Design → `spec.md`

Requirements, acceptance criteria, and **the verification method**. The method
field is what decides whether an agent can finish the ticket at all.

**Gate to leave:** criteria and `method` both explicit, every criterion
decidable, and a Specification Reviewer verdict recorded. For `method: live`,
the schedule, metric and number are fixed *before* any run. **[instruction]**,
→ **[mechanical]** at #142 and #180.

## 3 · Build, planning → `plan.md`

The tasks, the files that will change, the work order, **the radius**, the risks,
and the proof that will demonstrate completion — before any code is written.

**Gate to leave:** radius non-empty, proof named, and the radius intersects no
hard-stop path. This is the authoritative hard-stop check: it runs here because
here is where the radius first exists, and still before any code.
**[instruction]**, → **[mechanical]** at #143.

## 4 · Build, implementing → the diff

**Gate to leave:** every change inside the radius. **[unenforced]**,
→ **[mechanical]** at #150.

## 5 · Test → proof output

The suite's shape holds: `0 failed, 0 errors, 0 xfailed`, every deselected test
accounted for by an opt-in marker. For a behaviour change, the test that was
**red without the diff**, proven by stashing the source change and running it.

A refactor is the inverted case: no new test, no edited test, the suite passing
untouched. If you edited a test, it was not a refactor — say what moved.

**Gate to leave:** both recorded in `plan.md`'s proof block. **[instruction]**,
→ **[mechanical]** at #144 and #145.

## 6 · Review → `review.md`

The diff judged against `spec.md` and `REVIEW.md` — against the spec, not
against taste.

**Review runs before QA, deliberately.** QA is the most expensive stage in the
system: a client sitting, wall-clock time, the machine occupied. Spending it on
a diff a reviewer would reject wastes the scarcest resource there is.

**Gate to leave:** a verdict recorded. **[unenforced]**.

## 7 · QA → `qa.md`

The change exercised against a live Session, reported against criteria the QA
Operator did not write.

A verdict is a **rate over N trials**, never a single pass or fail — monsters,
lag and other players make one run meaningless. A pass inside the measurement's
noise is not a pass; it escalates.

**Gate to leave:** criteria met, and the Run Report names the commit it ran
against. **[unenforced]**, → **[mechanical]** at #155.

Skipped entirely when `method` is `suite` or `assent`.

## 8 · Document → doc updates or a cleared list

Either the documentation coupled to the changed paths is updated, or each
coupled document is listed in `plan.md`'s `docs_cleared` with a reason.

**Gate to leave:** nothing coupled left unaddressed. A gate that is always
cleared is worse than no gate — it records that documentation was considered
when it was not. **[unenforced]**, → **[mechanical]** at #185.

## 9 · Integrate → the PR

**The agent never merges.** It opens the PR and stops. Merge is a human action
until the escalation policy says otherwise, and even then only for ticket types
on the allowlist.

**Gate to leave:** every artifact present, verdict pass. **[instruction]**.

## 10 · Maintain → a new `intent.md`

Monitoring breaches a control band, invokes an analysis with no person in the
invocation path, and what it finds re-enters the pipeline as a new intent. Here
"production" is a running Session and "monitoring" is the analyzer reading
`telemetry.jsonl` and `trial_records/`.

Detection is deterministic and keeps an LLM out of the path entirely. A filed
intent lands as `needs-triage` and is never auto-claimed.

**[unenforced]**, → **[mechanical]** at #165.
