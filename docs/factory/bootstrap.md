# Working a ticket before the factory exists

Most of the factory is not built. This page is how to work a ticket anyway, and
it is the page to read before your first one.

## Four rules

**1. Hand-enforcement precedes tool-enforcement.** Until `factory next` and
`factory gate` exist, the stage sequence is a checklist in the PR body, and the
gate is a person reading it. The discipline is identical; only the enforcer
changes. **[instruction]**

**2. A command may not gate its own construction.** `factory prove suite` cannot
gate the PR that builds `factory prove suite`. Each stage's tooling is enforced
by hand for the PR that creates it, and mechanically from the next PR onward —
**and the PR body says which it was.** **[instruction]**

**3. Artifacts from day one.** Every ticket gets `.factory/<n>/` with at least
`intent.md` and `spec.md`, **committed before any source change**, as the first
commit on the branch. Not as a formality: committing them first is what makes a
later softening of a criterion show up in the diff as what it is. It is the only
version of "the spec is immutable to the Builder" available before the tooling
exists. **[instruction]**

**4. A change that adds a commitment adds an issue, in the same pass.** This is
the rule that stops things being forgotten. The traceability matrix on the
factory epic is the index, and it is worth nothing if it stops being complete.
**[instruction]**

## What is actually enforced today

Honestly, very little. Know which is which:

| Thing | Status |
| --- | --- |
| Ruff, Pyright on staged files | **[mechanical]** — pre-commit |
| Suite shape (`0 failed, 0 xfailed`) | **[instruction]** — until #144 |
| The test was red without the change | **[instruction]** — until #145 |
| Artifacts exist before code | **[instruction]** — until #189 |
| Edits stay inside the radius | **[unenforced]** — until #150 |
| You cannot finish with a missing artifact | **[unenforced]** — until #149 |
| Criteria written by someone other than the builder | **[unenforced]** — until #180 |
| Documentation kept current | **[unenforced]** — until #185 |
| Only the merge policy merges unreviewed | **[unenforced]** — the workflow exists (#194) but fires only from `dev`, and needs #151's checks; see [merge-policy.md](merge-policy.md#what-is-live-today) |

The last three are the gaps that no amount of care closes, so do not pretend
otherwise in a PR body. Say what you could not verify.

## The sequence, by hand

1. `git checkout -b issue/<n>-<slug>` off the working branch.
2. Write `.factory/<n>/intent.md` and `spec.md`. **Commit them alone**, before
   touching source.
3. Write `plan.md`: the files that will change, the order, the radius, and the
   proof that will demonstrate completion. Commit.
4. Build, inside the radius.
5. Prove: run the suite, and for a behaviour change, stash the source change and
   confirm the test goes red for the expected reason. Paste both outputs into
   the PR body.
6. Open the PR against the working branch, using
   `.github/PULL_REQUEST_TEMPLATE.md`. **The "Could not verify" section is not
   optional** and is the point of the template.
7. Stop. The agent never merges.

## Questions go in the PR, not into the session

Anything you genuinely cannot decide goes in the PR body under **"Decisions you
may want to reverse"**: what you chose, why, and what you would have needed to
choose differently. The maintainer reads them together, once.

Asking mid-session costs him an interruption per question and leaves the ticket
unfinished while he answers. Deciding and recording costs him one paragraph in a
review he was going to read anyway.

**Every question a maintainer cannot answer is a gap in the written plan.** The
fix is never to answer it once; it is to write the answer where the next agent
will find it — and to say so on the ticket, so the gap gets closed.

## When to stop and hand back

`AGENTS.md` already draws this line and it is unchanged here: a measured
constant, a running game client, a minimap trail, or a judgement that reduces to
watching the character. Stopping at one of these is compliance, not failure.

A half-finished ticket with a clear handoff is worth more than a guess. When the
exit-code contract exists, this is return code 3; today it is a sentence in the
PR body and a comment on the ticket.

## The checkpoint that ends the bootstrap

When `factory next` can drive the building of a factory ticket end to end, the
factory is self-hosting, and this page becomes history rather than instruction.
The first ticket it works unattended should be one of its own — which also means
the first unattended failure is one we can afford.
