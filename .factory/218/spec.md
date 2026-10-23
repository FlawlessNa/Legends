---
ticket: 218
stage: design
method: suite
criteria:
  - routing.resolve gives every v1 chain (no chain key, or chain 1) exactly the answer it gives today, proven by running today's routing tests unmodified and by a test over every chain committed under .factory/ that compares v1 answers before and after
  - a v2 chain (chain 2) routes through design, spec-review, build-planning, accept, build-implementing, document, review, qa and integrate, first match wins, from a ChainFacts value of chain, state and git-derived facts, with one red test per row
  - design holds until state.submitted is set, and spec-review holds until spec-review.md has verdict pass and its loop-stamped commit equals state.submitted, with changes-requested routing back to design
  - build-planning holds until plan.md has a non-empty radius that passes chain.radius_errors and its loop-stamped plan.commit equals state.submitted
  - accept holds until acceptance.md exists, equals state.accepted on spec_blob and base_sha, and its spec_blob equals the blob of spec.md at HEAD
  - build-implementing holds until proof.md has suite pass and red red or none, and no path outside .factory/ differs between proof.commit and HEAD
  - document holds until plan.md's docs_cleared is a list, not null, on the current proof, with factory doc check added to the row by #186
  - review holds until review.md has verdict pass and its loop-stamped commit is the commit that last wrote proof.md, so any proven Builder turn, including one that changes only plan.md, makes the review stale, with changes-requested routing back to build-implementing and fail blocking
  - a review loop terminates, proven by a test walking changes-requested, a new proof, a stale review, a new review and pass to integrate, including a Builder turn that changes only plan.md
  - qa blocks with "awaiting QA capability" for method live or both and is skipped for suite, park.md present blocks with its kind, and reaching configs/factory.toml's attempts or cycles cap blocks naming the cap
  - Stage gains spec-review and accept and keeps every v1 member, and VERDICTS is unchanged
  - factory/roles.py holds one row per role, designer, spec-reviewer, planner, builder, documenter, reviewer and orchestrator, each with its stage, where it runs (own-worktree, snapshot or worktree), write scope as radius-grammar entries, allowed commands and model stage key, and docs/factory/roles.md states the same table, checked equal by a test
  - configs/factory-models.toml maps spec-review and qa to complex, document and orchestrator to standard, drops plan and test, keeps fable unavailable, and adds an override when attempt_at_least 2 use complex, which models.py accepts as an integer fact read from the ticket's state, with tests for attempt 1 and attempt 2
  - configs/factory.toml holds attempts 2, cycles 2 and wip 1, read by routing, and a missing or malformed file is a clear error
  - docs/factory/stages.md describes the v2 table beside the v1 one, its glob wording for radius entries is corrected to the radius grammar, and the full suite is green
specified_by: claude
specified_at: 2026-10-23
---

# Spec: routing v2, roles.py and the model table

## Source

- Issue #218 (S5), as updated on 2026-10-22 with the maintainer's decisions: retry escalation, Fable unavailable, the Documenter kept and placed before review.
- `docs/factory/design.md` §2, §5 and §6.
- The branch is stacked on #219 (`state.json`), which is stacked on #207, and has #139 via `dev`.

## Shape

- **`routing.py`.**
  - `resolve(repo_root, branch)` reads the chain. A v1 chain goes to today's `ROWS`, untouched.
  - A v2 chain is read through `gather(repo_root, ticket) -> ChainFacts`. That is the impure part: it holds `state.load` plus the git facts:
    - the blob of `spec.md` at HEAD;
    - whether source differs between `proof.commit` and HEAD;
    - the commit that last wrote `proof.md`.
  - `ROWS_V2` then decides from `ChainFacts` alone, first match wins. A missing fact, such as git failing, makes its row hold, never pass.
  - `UnknownChainVersion` (#139) propagates as misuse.
- **`roles.py`** is a frozen table. `role_for(stage)`, `allowed(role, command)` and `scope(role, ticket)` are what #163, #222 and #159 read.
- **`models.py`.**
  - `FACTS` gains `attempt_at_least`, an integer compared with `>=`. `Override.when` becomes `Mapping[str, bool | int]`, and the validation rejects a wrong type per key.
  - `resolve` gains an optional `state` argument. `factory model <n>` passes `state.load(...)` for v2 chains. For v1 it passes none, so the escalation never fires on v1.
- **`configs/factory.toml`** is read by a small loader beside the models table. Its errors are a `TableError`-like misuse.

## Verification method: suite

- **Red tests:** one per v2 row, the termination walk, each block reason, roles equality with `roles.md`, the escalation at attempts 1 and 2, the `factory.toml` errors, and the v1 equality test over the committed chains.
- **v1 safety:** `test_routing.py` and `test_models.py` pass unmodified, except where a test asserts the table's key list, which is named in the plan.

## Decisions I made

- **Two tables, chosen by `Chain.version`,** not one table with version guards in every row. A v1 row can then never be broken by a v2 change.
- **Git facts are gathered once per resolve,** and a missing fact holds the row. Routing never passes a stage on a fact it could not read.
- **`document` is a real row now,** with its gate completed by #186. Until then it advances on `docs_cleared` alone, as v1 does.

## Not in scope

- Writing any of the v2 artifacts: #222, #145, #186 and #159.
- The role write-scope enforcement (#163) and the command allowlist enforcement (#222).
