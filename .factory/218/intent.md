---
ticket: 218
stage: plan
accepted_by: nassim
accepted_at: 2026-10-23
---

# Intent: route a v2 ticket through the agreed lifecycle, so its loops end, without disturbing any v1 ticket

## Problem statement

Today's routing table cannot drive the factory the maintainer agreed to:
- **It never reads the spec-review verdict.** The file only has to exist. Eight of nine committed reviews say `changes-requested`, and every one let source through.
- **A rejected review can never be left.** After `review.md: changes-requested` it routes back to the Builder, and nothing the Builder can do moves it on (design §3, d1).
- **Its loops are uncapped,** and it has no idea of submission, acceptance, a proof the factory loop wrote, or a parked ticket.
- **Model routing has no notion of retries.** A capped stage spends two identical cheap attempts and then parks. The maintainer decided on 2026-10-22 that a second attempt escalates.

## Split, 2026-10-23

On its spec review's advice, this ticket was split. The routing rows below moved to **#237**. This ticket delivers `roles.py`, the model table and `configs/factory.toml`, plus the Stage enum's two new members and the design.md amendments. The outcome below is shared between the two tickets.

## Proposed outcome

A v2 ticket (`intent.md: chain: 2`) routes through the agreed stages:
- design
- spec-review
- build-planning
- accept
- build-implementing
- document
- review
- qa
- integrate

Its verdicts are read, each against the exact commit it judged, and its cycles and attempts are capped. Every v1 ticket keeps today's routing unchanged, because every roadmap ticket is still worked by hand under v1. A role table names who does each stage, what it may write and which commands it may run, and the model table gains the decided stages and the retry escalation.

## Affected users and systems

- `factory/routing.py`, `factory/models.py`, and a new `factory/roles.py`.
- `configs/factory-models.toml` and a new `configs/factory.toml`.
- `docs/factory/stages.md` and `docs/factory/roles.md`.
- The tests for each.

## Constraints

- v1 routing must not change for any v1 chain: the hand-worked process builds everything else on it.
- Routing stays a first-match-wins table. It may gather facts with git, but it decides from those facts alone.

## Open questions

Acceptance is inferred. The maintainer accepted the roadmap, and on 2026-10-22 made the model-table decisions themselves (escalate on retry; Fable unavailable; Documenter kept).
