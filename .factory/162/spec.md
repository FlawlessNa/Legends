---
ticket: 162
stage: design
method: suite
criteria:
  - the table lives in factory/models.toml and is read with stdlib tomllib, adding no runtime dependency
  - resolution routes a stage to a tier, and a tier to the first available model in its chain
  - unavailable models are declared in the table, never discovered, so two callers get the same answer
  - an override beats the stage table, and when several overrides match the first in file order wins
  - an unknown stage, an unknown tier, a tier whose whole chain is unavailable, and a missing or malformed table are each MISUSE, never a silent fallback
  - the resolution carries the reason for itself - which rule fired - and a record line for the chain
  - factory model <ticket> prints the resolution in --json and in prose, from one payload
  - the stage vocabulary is imported from factory.routing, not respelled
  - artifacts.md names the front-matter field the Foreman writes, and models.toml is on the protected paths list
specified_by: claude
specified_at: 2026-10-18
reviewed_by: see spec-review.md
---

# Spec: the model routing table

## Source

Issue #162, body amended before building (see its comment). The amendment
replaced three model ids with three tiers, moved `qa` and `plan` off Haiku,
replaced `deploy` with the stages this factory actually has, and replaced YAML
with TOML. The amended body is the source; the original is not.

## Tiers, not models

    complex  = ["fable", "opus"]
    standard = ["sonnet"]
    trivial  = ["haiku"]

A tier resolves to the **first model in its chain that is not declared
unavailable**. `unavailable = ["fable"]` is the state of the subscription today,
so `complex` resolves to `opus`; deleting that one entry is the whole of
enabling Fable.

Availability is **declared, not discovered**. A resolver that asks the network
which models exist is not a function of its inputs: it answers differently on
different days, and the Foreman's choice stops being reproducible from the
table. The cost of declaring is a stale entry, which is a wrong answer a human
can see and fix. The cost of discovering is a wrong answer nobody can
reconstruct.

## Which stage gets which tier

| Stage | Tier | Why |
| --- | --- | --- |
| `plan` | `standard` | `intent.md` decides what the ticket is |
| `design` | `complex` | a wrong spec is paid for by every later stage |
| `spec-review` | `complex` | it is the gate that catches that error |
| `build-planning` | `standard` | the radius is a judgement, but a narrow one |
| `build-implementing` | `standard` | Test, Review and QA sit downstream |
| `test` | `standard` | |
| `review` | `complex` | judging a diff is harder than writing one |
| `qa` | `standard` | reading a Run Report wrong merges a broken bot |
| `document` | `standard` | |
| `integrate` | — | CI decides the merge; no agent runs (#194) |

`integrate` is absent from the table deliberately, and asking for it is a
`MISUSE` rather than a default: a caller asking which model runs Integrate has
misunderstood that nothing does.

`trivial` is reserved and routed to by no stage. It exists so the tier
vocabulary is complete; if a stage is ever routed to it, that is a decision to
argue in a ticket rather than a budget to quietly spend.

## Overrides

    [[overrides]]
    when = { touches_hard_stop = true }
    use  = "complex"

An override names one or more facts about the ticket and a tier to use instead
of the stage's. **An override beats the stage table**, and when several match,
**the first in file order wins** — the same rule `factory next` uses for its
rows, for the same reason: a reader must be able to predict the answer from the
file without ranking the overrides by how specific they look.

Three ship with the table: a ticket touching a hard-stop path, a `method: live`
ticket, and an escalated retry (#160). All three route to `complex`, which is
the only direction an override is allowed to move the tier in this ticket —
there is no case yet for routing a stage *down*, and adding one is a decision,
not a configuration.

## Failing loudly

Every one of these is `MISUSE` (exit 2):

- a stage not in the table, `integrate` included
- a tier named by a stage or an override that the `[tiers]` block does not define
- a tier whose every model is declared unavailable
- `models.toml` missing, unparseable, or missing a required block
- an override naming a fact the resolver does not know how to evaluate

The last one matters most and is the easiest to get wrong. An unknown key in a
`when` clause must not quietly evaluate false: an override that silently never
fires is a policy the maintainer believes is in force and is not.

**None of these fall back to the strong model.** A silent fallback to `opus`
turns a typo into a bill, and a bill is the one error class this repo has no
test for.

## Recording the choice

The resolution carries a `record` line, and `artifacts.md` names the
front-matter field — `model` — that the stage artifact carries. **This ticket
does not write it.** Writing front matter into an artifact is the Foreman's
action (#159), and a resolver that also writes is a resolver that cannot be
called to ask a question.

## Radius

Named in `plan.md`, not here.

## What this does not do

- Does not start a session, pass a `--model` flag, or know how a harness is
  invoked. #159 does.
- Does not verify that any model alias is real. It cannot: see `intent.md`.
- Does not add the Escalation policy's trust dial (#160). It reads an
  `escalated` fact if a caller supplies one; nothing sets it yet.
