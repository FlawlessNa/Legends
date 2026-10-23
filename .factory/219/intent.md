---
ticket: 219
stage: plan
accepted_by: nassim
accepted_at: 2026-10-23
---

# Intent: the factory loop's memory, kept where no session can trip over it, and a way to hand a ticket back

## Problem statement

The factory loop (#159) has to remember things across turns and crashes:
- which stage a ticket is in;
- how many attempts and review cycles it has used;
- which worker is running, and the commit its turn started from;
- what was submitted;
- whether the ticket is parked.

The first design kept this in the ticket's branch, and the review showed why
that fails. Several processes commit in one worktree, and every worker's diff
fills with the loop's files. A worker also has no way to say "I cannot go on;
a person must decide" except by stopping, which looks like any other failure.

## Proposed outcome

The loop's state for each ticket lives in one small JSON file under the
repository's shared git directory. It is written atomically, survives a crash,
and is rendered to a readable log once, just before the PR. A worker hands a
ticket back with `factory park`, which leaves a `park.md` the loop and routing
can read.

## Affected users and systems

- A new `factory/state.py`.
- `factory/cli.py`, for the `park` command.
- New tests.
- `docs/factory/artifacts.md`, for the `park.md` contract.

## Constraints

- Nothing here writes into a ticket worktree except `park.md`.
- No dependency: JSON from the standard library.

## Open questions

Acceptance is inferred. The maintainer accepted the roadmap and asked for work
to continue (2026-10-23).
