---
ticket: 218
stage: design
method: suite
criteria:
  - the Stage enum gains spec-review and accept and keeps every v1 member, and routing's v1 ROWS, VERDICTS and test_routing.py are unchanged
  - factory/roles.py holds one row per role, designer, spec-reviewer, planner, builder, documenter, reviewer and orchestrator, each with its stages, where it runs (primary, own-worktree, snapshot or worktree), its write patterns and its allowed commands
  - write patterns are globs matched the way merge.py matches paths (full_match, ** crosses directories), with a leading ! excluding, so the documenter's scope can say docs/**, **/AGENTS.md (excluding .claude/**), CONTEXT.md and .factory/<n>/park.md while excluding every merge.POLICY hard-stop and protected docs path, taken from merge.py rather than copied, and scope(role, ticket) substitutes <n>
  - the builder's scope is its static patterns plus the marker RADIUS, which scope returns unexpanded and which means plan.md's radius within acceptance.radius, for #163 to enforce
  - allowed(role, argv) matches an allowlist entry against the command words that follow the global options, so "spec submit" matches both ["spec", "submit"] and ["--json", "spec", "submit"], and hook is allowed for every role because the harness invokes it
  - role_for(stage) gives the worker role for every v2 stage that has one and None for accept, integrate, qa (no worker until the QA phase) and the v1-only stages plan and test, and the v1 roles stay documented for hand-worked tickets
  - docs/factory/roles.md states the v2 table and keeps the v1 table under its own heading, and a test checks the v2 table equals roles.py
  - configs/factory-models.toml maps spec-review and qa to complex and document to standard, drops plan and test, keeps fable unavailable, and gains a [roles] block giving the orchestrator standard, which models.py loads and answers through resolve_role(table, role), where a key that is not a role in roles.py, or a role that has stages, is a TableError, and accept joins integrate as a stage no model is resolved for
  - an override may use attempt_at_least, an integer of at least 2 that rejects booleans, and it fires when the attempt being dispatched, which is state.dispatched(state, stage).attempt from #219 computed on the state before the dispatch is recorded, is at least that number, so a stage's second dispatch escalates to complex and a new stage's first does not, and factory model <n> reports the model for the next dispatch
  - factory model <n> passes the ticket's state for a v2 chain and no state for a v1 chain, so escalation never fires on v1, and factory model --stage S without a ticket never escalates
  - configs/factory.toml requires attempts, cycles and wip (positive integers) and launcher (a string), accepts worker_timeout_min and poll_s as optional until the ticket that reads them supplies their values, is read from the session's own checkout like the model table, and an unknown key, a missing required key or a wrong type raises ConfigError, which is exit 3 with the key named, and v1 routing never reads it
  - docs/factory/design.md reverses R9 and places document after the proof and before review in §2, adds the Documenter to §5, §6 and §8, removes the Document stage from §11, marks §6's review-staleness sentence as settled by #237, adds #237 to §10's build order, and the Supersedes notes in stages.md, roles.md and artifacts.md name #237 for the routing rows
  - test_cli.py's test_model_names_the_rule_that_fired and the shipped-table model test are named in the plan as changed, because qa moves to complex, and the full suite is green
specified_by: claude
specified_at: 2026-10-23
revised_after: spec-review-2.md (changes-requested, R1-R4)
---

# Spec: roles.py, the model table, and configs/factory.toml

## Source

- Issue #218, with the maintainer's 2026-10-22 decisions: retry escalation, Fable unavailable, the Documenter kept and placed before review.
- `docs/factory/design.md` §5, §6 and §8.
- **The routing rows moved to #237** on the spec review's advice. Findings 1, 2, 5, 6, 11 and 12 are carried there verbatim. This ticket settles 3, 4, 7, 8, 9, 10 and the `cli.py` part of 13.

## Shape

- **`factory/roles.py`.**
  - A frozen `Role`: name, stages, `runs_in` (`primary | own-worktree | snapshot | worktree`), `writes` (glob patterns, with `!` to exclude), `commands` (word sequences).
  - `ROLES`, `role_for(stage)`, `scope(role, ticket)` and `allowed(role, argv)`.
  - **Write scopes:**
    - Designer: `.factory/<n>/intent.md`, `spec.md`, `answers.md`.
    - Spec Reviewer: `spec-review.md`.
    - Planner: `plan.md`.
    - Builder: `RADIUS`, `tests/**`, `.factory/<n>/plan.md`, `park.md`.
    - Documenter: `docs/**`, `!docs/adr/**`, `!docs/agents/typing.md`, `**/AGENTS.md`, `CONTEXT.md`, `.factory/<n>/plan.md`.
    - Reviewer: `review.md`.
    - Orchestrator: nothing.
  - **Commands:**
    - Designer: `spec submit`, `park`, `next`.
    - Judges: `park`.
    - Planner: `plan check`.
    - Builder: `park`, `next`, `plan check`.
    - Documenter: `doc check`, `park`, `next`.
    - Orchestrator: `status`, `run`, `feature new`, `next`.
    - `hook` is always allowed.
- **`models.py`.**
  - A `[roles]` block resolves by role name, for roles with no stage (the Orchestrator).
  - `NO_AGENT` becomes a set: `{integrate, accept}`.
  - `attempt_at_least` is an integer fact, so `Override.when` becomes `Mapping[str, bool | int]`. Validation is per key: `method_live` must be a bool, and `attempt_at_least` an int ≥ 2 and not a bool.
  - `resolve(table, stage, chain, state=None)` computes the attempt being dispatched via #219's `dispatched`.
- **`configs/factory.toml`** is loaded by `factory/config.py`, read from the session's checkout, so a ticket branch cannot raise its own caps. Errors are exit 3, like `TableError`.
- **`cli.py`.** `_model` passes state for v2, and catches `StateError` and `UnknownChainVersion` as exit 3 with the reason.

## Verification method: suite

**Red tests:**
- the role table and each scope, including the Documenter's exclusions;
- the `RADIUS` marker;
- `allowed` with multi-word commands and `hook`;
- `role_for` for every v2 stage;
- the `roles.md` equality;
- the `[roles]` block and accept's lack of a model;
- escalation at the first and second dispatch, after a stage change, and with `--stage` alone;
- `attempt_at_least` rejecting `true`, `1` and `"2"`;
- `factory.toml`'s errors;
- `_model` on a v2 chain with malformed state, giving exit 3.

**Changed tests:** `test_model_names_the_rule_that_fired` (qa moves to opus) and the shipped-table test. Both are named in the plan.

## Decisions I made

- **The split.** The reviewer offered it as optional, and I took it. This ticket unblocks #163, #222, #143 and #152, and #237 can settle its contracts without holding them up.
- **Write scopes are globs, not radius entries.** Radius entries must compare with each other, but a scope only matches paths. The two grammars stay separate.
- **The model table and `factory.toml` are always read from the session's checkout.** The same rule as #216: a ticket branch cannot change its own policy.

## Not in scope

- **An obligation on #159:** resolve a worker's model *before* recording its dispatch in `state.json`. Otherwise the first dispatch of a stage escalates. A test here pins the before-recording semantics.
- `worker_timeout_min` and `poll_s` values: supplied by #220's launcher defaults and #159, which read them. `AGENTS.md` keeps timing constants out of a builder's hands.
- Until #237 lands, `factory model <n>` routes a v2 chain with the v1 rows. This is harmless, because no v2 chain exists before #222. The PR says so.

- The routing rows (#237).
- Enforcing write scopes (#163) and command allowlists (#222).
