---
ticket: 197
stage: design
method: assent
criteria:
  - README.md carries the Decide and record rule near the top, beside the enforcement markers
  - roles.md defines an escalation as exactly the three things the human owns, and says everything else is delegated
  - bootstrap.md says questions are batched into the PR body under a named heading, never asked mid-session
  - stage-template.md gains a Decide and record slot so new stages inherit it
  - every existing Stop and hand back section is reviewed, and anything that is not one of the three reasons is moved to Decide and record
  - no real stop is weakened: a measured constant, a running client, or a hard-stop path still stops the ticket
  - the suite is unchanged, this being documentation only
specified_by: claude
specified_at: 2026-10-17
reviewed_by: see spec-review.md
---

# Spec: let agents decide

## Source

Issue #197. Written in response to #194 producing nothing.

## The rule being added

> **Decide and record.** When the answer is not in the repo and is not one of
> the three things the maintainer owns, choose the conservative option, write
> the choice and its reasoning into the artifact under "Decisions I made", and
> continue. Do not stop to ask what you could defensibly decide.
>
> A decision recorded and wrong is cheap: it is visible in a diff and reversible
> in a comment. A ticket that produced nothing is not.

## What still stops a ticket

Unchanged, and this is the half that must not erode:

- A hard-stop path in `AGENTS.md`
- A measured constant, a running client, a minimap trail, or a judgement that
  reduces to watching the character
- Risk and trust appetite; product priority

## Verification method: assent

Settled by the maintainer agreeing the documents now say an agent may decide.
The real test is behavioural and comes later: does the next ticket produce a PR
instead of a question list.

## Known gap

`specified_by` is the Builder again. The review stand-in is the mitigation.
