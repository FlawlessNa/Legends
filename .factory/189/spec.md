---
ticket: 189
stage: design
method: suite
criteria:
  - factory hook session-start reports the chain state for the branch ticket and never blocks
  - factory hook pre-tool-use denies a write outside .factory/ when spec.md or spec-review.md is missing, on an issue/<n>-* branch only
  - factory hook stop denies finishing when source changed and plan.md carries no proof
  - none of the three hooks fire on a non-ticket branch
  - writes under .factory/ are always allowed, so the chain can be created
  - decision logic is unit-tested from a branch name plus a filesystem state, with no harness
  - per-call latency of pre-tool-use is measured and recorded against a stated budget of 150ms
  - the override is documented in factory/AGENTS.md and lives in settings.local.json
  - the spec-review artifact is defined in docs/factory/artifacts.md and required by the stage 2 gate
specified_by: claude
specified_at: 2026-10-16
reviewed_by: null
---

# Spec: bootstrap enforcement

## Scope addition, agreed with Nassim

The **review stand-in** lands here rather than in a new ticket. It is the same
mechanism: an artifact the hooks stat.

`.factory/<n>/spec-review.md` carries the verdict, and must quote at least one
criterion and judge it. Not a boolean in `spec.md`, which the Builder also
writes.

Three layers, and the limit is stated honestly:

1. The reviewer writes its own file. To forge one convincingly you must read
   the spec against the intent, which is the review. The forgery and the work
   converge.
2. Ordering is checkable by `git log`: the review commit touches only
   `.factory/<n>/`, and lands before any source commit.
3. `pre-tool-use` refuses source edits while it is missing.

**None of this proves a different agent reviewed it.** Only #163 does, by
spawning the reviewer so the Builder never has the chance. Until then this
shapes cost rather than preventing.

## Verification method: suite

The decision logic is a pure function of a branch name and a filesystem state,
so it is unit-testable without the harness. That the harness actually invokes
the hooks is not -- see Could not verify in the PR.

## Known gap in this spec

`specified_by` and the Builder are the same agent, and `reviewed_by` is null at
the time of writing. This ticket is what makes that gap visible in future ones.
