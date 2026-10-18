# The stages

Each stage consumes the previous stage's artifact, produces its own, and refuses
to start until its gate passes. Enforcement markers are defined in
[README.md](README.md).

**This page is the only home of stage instructions.** The entry skill
(`.claude/skills/factory/SKILL.md`) and, later, a role's system prompt (#163)
point here and copy nothing. If you find stage instructions anywhere else, they
are a copy that has drifted or is about to; delete the copy, not this.

## How to read a stage section

Every section has the same seven slots, in this order. A new stage starts from
[stage-template.md](stage-template.md).

| Slot | Answers |
| --- | --- |
| **Trigger** | Which stage this is, and the state of the chain that names it |
| **Entry gate** | What must already be true before any work starts |
| **Decide and record** | What this stage decides for itself rather than asking |
| **Context** | What to read first, beyond the standing list |
| **The work** | What to do, ending at an artifact — never at a merge |
| **The oracle** | Exactly how done is demonstrated |
| **Artifacts** | What the stage leaves behind |
| **Stop and hand back** | When to stop, beyond the standing list |

Three things hold for every stage and are not repeated in each section:

- **When an entry gate fails:** comment on the ticket naming what is missing,
  relabel it `needs-info`, and stop. Do not produce the missing thing yourself
  unless the Trigger has routed you to the stage that owns it. **[instruction]**
- **Context** always starts with
  [`AGENTS.md` → Read before you explore](../../AGENTS.md#read-before-you-explore)
  and the `AGENTS.md` of each package the stage touches. A section lists only
  what it adds.
- **Stop and hand back** always includes
  [`AGENTS.md` → When to stop and hand back](../../AGENTS.md#when-to-stop-and-hand-back).
  A section lists only what it adds. Once the exit-code contract exists
  (`factory/AGENTS.md`), every stop here is exit code 3.

The stage names in each Trigger are the identifiers `factory next` (#140) will
report. They are proposed here and #140 settles them. Until it lands, the stage
is computed by the stub table in the entry skill.

## 1 · Plan → `intent.md`

### Trigger

`plan`. Routed here when `.factory/<n>/intent.md` does not exist, or its
`accepted_by` is `null`. Role: Clerk ([roles.md](roles.md)).

### Entry gate

An issue `<n>` exists and its body says what is wanted. Nothing upstream is
required: this is the first stage.

### Context

[`CONTEXT.md`](../../CONTEXT.md), so the problem is stated in the project's
vocabulary rather than a synonym it rejects. Nothing else: intent precedes any
decision about how.

### The work

What is wanted, why, and under which constraints, in the originator's language
before any process touches it. Sections: problem statement, proposed outcome,
affected users and systems, constraints, open questions.

The issue **body** is the source. A correction that lives only in a comment
does not correct it: ask for the body to be amended rather than building from
the comment.

### The oracle

Accepted by the maintainer. This is not a peer review — there is no ground
truth for an intent except the originator. **[instruction]**

`accepted_by` records the maintainer's acceptance, never the Clerk's own view
that the intent is sound. Where acceptance is inferred — the maintainer wrote the
issue body — say so under open questions.

### Artifacts

`.factory/<n>/intent.md`, front-matter per
[artifacts.md → `intent.md`](artifacts.md#intentmd). It is committed together
with `spec.md` as the first commit on the branch
([bootstrap.md](bootstrap.md), rule 3).

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- The request is too vague to shape into the five sections.
- The maintainer has not accepted it. A Clerk never fills `accepted_by` on its
  own judgement.

## 2 · Design → `spec.md`

### Trigger

`design`. Routed here when `intent.md` is accepted and either `spec.md` or
`spec-review.md` is missing. Role: Specifier, then the Specification Reviewer
for the gate.

### Entry gate

`intent.md` exists and `accepted_by` is not `null`.

### Context

- `CONTEXT.md` → **Invariant** and **Expectation**. The distinction decides
  `method`.
- [triage-labels.md → What `ready-for-agent` means here](../agents/triage-labels.md#what-ready-for-agent-means-here),
  which draws the same line at ticket level.
- The ADRs in [`docs/adr/`](../adr/) touching the area the intent names.

### The work

Requirements, acceptance criteria, and **the verification method**. The method
field is what decides whether an agent can finish the ticket at all.

The field contract, the decidability test for a criterion, and why the radius is
not recorded here are in [artifacts.md → `spec.md`](artifacts.md#specmd).

The Specification Reviewer then reads `intent.md` against `spec.md` and writes
`spec-review.md` — its own file, quoting at least one criterion and judging it.
A verdict the Builder could have written into `spec.md` itself is not a review;
see [artifacts.md → `spec-review.md`](artifacts.md#spec-reviewmd) for why the
file, and what it does and does not buy. Until #180 there is no such role; the
stand-ins are in [roles.md → Today](roles.md#today).

### The oracle

Criteria and `method` both explicit, every criterion decidable, and
`spec-review.md` present with a verdict that quotes a criterion. For
`method: live`, the schedule, metric and number are fixed *before* any run.

**[mechanical]** as of #189 for the *existence* of the review — the `PreToolUse`
hook refuses every edit outside `.factory/` until it is there. Whether the
review is any **good** stays **[instruction]** until #180, and a green hook is
not a reviewed spec.

### Artifacts

`.factory/<n>/spec.md`, committed with `intent.md` before any source change.
From that commit on, any change to a criterion is an amendment visible in
`git log`.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- No offline or live method can settle the intent.
- The intent and the spec do not match.
- `reviewed_by` is `null` and nobody but the Specifier is available to fill it.
  A Specifier never reviews its own spec. Where the same agent wrote the spec
  and will build it, record that as a known gap in the spec itself.

## 3 · Build, planning → `plan.md`

### Trigger

`build-planning`. Routed here when `spec.md` is reviewed and `plan.md` does not
exist. Role: Builder.

### Entry gate

`intent.md` accepted; `spec.md` present; `spec-review.md` present with a verdict.

### Context

- The code the change will touch — the radius is an implementation fact, known
  only once the code has been read.
- [`AGENTS.md` → What you may change](../../AGENTS.md#what-you-may-change), which
  is the hard-stop list the gate checks against.
- The ADRs governing the paths in the radius.

### The work

The tasks, the files that will change, the work order, **the radius**, the risks,
and the proof that will demonstrate completion — before any code is written.

If the work splits, the split follows
[artifacts.md → Tickets and tasks](artifacts.md#tickets-and-tasks). A task that
needs its own `spec.md` is a ticket: go back to stage 2 rather than give it one.

### The oracle

Radius non-empty, proof named, and the radius intersects no hard-stop path. This
is the authoritative hard-stop check: it runs here because here is where the
radius first exists, and still before any code. **[instruction]**,
→ **[mechanical]** at #143.

### Artifacts

`.factory/<n>/plan.md`, front-matter per
[artifacts.md → `plan.md`](artifacts.md#planmd), with the `proof` fields still
`null`. Committed before any source change.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- The radius intersects a hard-stop path. That needs the maintainer's scope
  approval ([roles.md → The human's role](roles.md#the-humans-role)).

## 4 · Build, implementing → the diff

### Trigger

`build-implementing`. Routed here when `plan.md` exists and `proof.suite` is
`null`. Role: Builder.

### Entry gate

`plan.md` committed, with a non-empty radius.

### Context

- The radius in `plan.md` — the only paths you may touch.
- [typing.md](../agents/typing.md), because pre-commit checks every file you
  stage. **[mechanical]**

### The work

Make the change, touching only paths in the radius. A behaviour change brings
the test that will prove it; stage 5 proves it was red.

### The oracle

Every change inside the radius: each path in
`git diff --name-only <working branch>...HEAD` matches a glob in `radius`.
**[unenforced]**, → **[mechanical]** at #150.

When this holds and the work is done, continue to stage 5 in the same role.

### Artifacts

Commits on the ticket's branch. Nothing under `.factory/<n>/` changes here.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- The work needs a path outside the radius. Do not write it, and do not widen
  the radius after code has been written to cover it.

## 5 · Test → proof output

### Trigger

`test`. Routed here when stage 4's oracle holds and `plan.md`'s proof block is
not yet filled. Role: Builder.

### Entry gate

The diff is confined to the radius.

### Context

- [testing.md → Proving a new test earns its place](../agents/testing.md#proving-a-new-test-earns-its-place),
  the stash procedure, and its refactor case.
- [`AGENTS.md` → Verifying your work](../../AGENTS.md#verifying-your-work), the
  green baseline and what a red `lab` test means.
- [movement-invariant-catalogue.md](../planning/movement-invariant-catalogue.md),
  for the invariant ids the diff bears on.

### The work

The suite's shape holds: `0 failed, 0 errors, 0 xfailed`, every deselected test
accounted for by an opt-in marker. For a behaviour change, the test that was
**red without the diff**, proven by stashing the source change and running it.

A refactor is the inverted case: no new test, no edited test, the suite passing
untouched. If you edited a test, it was not a refactor — say what moved.

Under [bootstrap.md](bootstrap.md), the Builder then opens the PR (its step 6)
and stops. Stages 6 to 9 run on the open PR.

### The oracle

Both recorded in `plan.md`'s proof block. **[instruction]**,
→ **[mechanical]** at #144 and #145.

### Artifacts

- `plan.md` → `proof`: `red_test` (the test's node id, or `null` for no behaviour
  change), `suite`, and `red_output_sha`, which stays `null` until #145 defines
  what it hashes.
- Both outputs, pasted into the PR body.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- The new test passes without the change. It is not testing the change.
- The change can only be shown correct against a running client. That is a
  `method: live` ticket that was specified as something else; it goes back to
  stage 2.

## 6 · Review → `review.md`

### Trigger

`review`. Routed here when `proof.suite` is filled and `review.md` does not
exist. Role: Reviewer.

### Entry gate

`plan.md`'s proof block is filled.

### Context

- `spec.md` — the criteria the diff is judged against.
- [code-review.md](../agents/code-review.md), the five checks.
- `docs/factory/review-policy.md` — not written yet (#152). Until it exists,
  `code-review.md` is the only written policy.

### The work

The diff judged against `spec.md` and `docs/factory/review-policy.md` —
against the spec, not
against taste.

**Review runs before QA, deliberately.** QA is the most expensive stage in the
system: a client sitting, wall-clock time, the machine occupied. Spending it on
a diff a reviewer would reject wastes the scarcest resource there is.

### The oracle

A verdict recorded. **[unenforced]**.

### Artifacts

`.factory/<n>/review.md`: the findings and the verdict. Its front-matter is not
yet contracted in [artifacts.md](artifacts.md); #152 does that.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- The diff does something the spec never asked for.

## 7 · QA → `qa.md`

### Trigger

`qa`. Routed here when the review verdict is a pass, `method` is `live` or
`both`, and `qa.md` does not exist. Role: QA Operator.

Skipped entirely when `method` is `suite` or `assent`.

### Entry gate

A passing review verdict, and `spec.md` naming the schedule, the metric and the
number.

### Context

`CONTEXT.md` → **Session**, **Trial**, **Trial schedule**, **Trial record** and
**Expectation**.

### The work

The change exercised against a live Session, reported against criteria the QA
Operator did not write.

A verdict is a **rate over N trials**, never a single pass or fail — monsters,
lag and other players make one run meaningless. A pass inside the measurement's
noise is not a pass; it escalates.

### The oracle

Criteria met, and the Run Report names the commit it ran against.
**[unenforced]**, → **[mechanical]** at #155.

### Artifacts

`.factory/<n>/qa.md`, the Run Report, containing what
[artifacts.md → `qa.md` and `review.md`](artifacts.md#qamd-and-reviewmd)
requires.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- This stage needs a running client, which is on the standing list. Today an
  agent stops here every time.
- The Session will not start, or the client is not ready.
- A pass inside the measurement's noise.

## 8 · Document → doc updates or a cleared list

### Trigger

`document`. Routed here when every verdict the method requires is a pass, and
`docs_cleared` is `null`. Role: Documenter. This stage's position is open: #186.

### Entry gate

A passing review verdict, and a passing `qa.md` when `method` is `live` or
`both`.

### Context

[domain.md](../agents/domain.md), because a document changed here must use the
glossary's terms.

### The work

Either the documentation coupled to the changed paths is updated, or each
coupled document is listed in `plan.md`'s `docs_cleared` with a reason.

Until #182 declares the coupling, which documents are coupled is decided by
reading the diff.

### The oracle

Nothing coupled left unaddressed. A gate that is always cleared is worse than no
gate — it records that documentation was considered when it was not.
**[unenforced]**, → **[mechanical]** at #185.

### Artifacts

Documentation updates on the branch, and `plan.md` → `docs_cleared` set — `[]`
when every coupled document was updated (see
[artifacts.md → `plan.md`](artifacts.md#planmd)).

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- A coupled document describes something you no longer understand.

## 9 · Integrate → the PR

### Trigger

`integrate`. Routed here when every artifact the method requires is present and
`docs_cleared` is not `null`. Role: Integrator.

### Entry gate

Every artifact present, every verdict a pass.

### Context

[`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md).

### The work

**The agent never merges.** It opens the PR, if one is not already open, and
stops. Merge is a human action, or CI's when
[merge-policy.md](merge-policy.md) holds — never the agent's. Run
`factory merge check <pr>` to see which, and say so in the PR.

### The oracle

Every artifact present, verdict pass. **[instruction]**.

### Artifacts

The open PR, written to the template. After a human merges it, the closed
ticket.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- Always, once the PR is open. An agent's work ends there.
- Any gate is missing its artifact.

## 10 · Maintain → a new `intent.md`

### Trigger

`maintain`. Never routed from an existing ticket's chain: a finished Session
breaches a control band, and the analysis that runs has no person in its
invocation path. No role in [roles.md](roles.md) owns it.

### Entry gate

A finished Session's `telemetry.jsonl` and `trial_records/`, and the bands they
are judged against (#165).

### Context

`CONTEXT.md` → **Session**, **Telemetry Record** and **Trial record**;
[ADR 0001](../adr/0001-logging-architecture.md), which fixes the telemetry
envelope the analyzer reads.

### The work

Monitoring breaches a control band, invokes an analysis with no person in the
invocation path, and what it finds re-enters the pipeline as a new intent. Here
"production" is a running Session and "monitoring" is the analyzer reading
`telemetry.jsonl` and `trial_records/`.

Detection is deterministic and keeps an LLM out of the path entirely.

### The oracle

A breach files an intent; no breach files nothing.
**[unenforced]**, → **[mechanical]** at #165.

### Artifacts

A new ticket with its own `intent.md`, labelled `needs-triage`.

### Decide and record

Anything not listed below, and not one of the four things the maintainer owns,
is this stage's to decide: take the conservative option, record it under
"Decisions I made", continue. See
[README → Decide and record](README.md#decide-and-record).

### Stop and hand back

- Always, once the intent is filed. A filed intent lands as `needs-triage` and
  is never auto-claimed.
