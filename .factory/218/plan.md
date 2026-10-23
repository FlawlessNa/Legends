---
ticket: 218
stage: build
radius:
  - factory/roles.py
  - factory/config.py
  - factory/models.py
  - factory/routing.py
  - factory/cli.py
  - factory/AGENTS.md
  - configs/factory-models.toml
  - configs/factory.toml
  - tests/test_factory/test_roles.py
  - tests/test_factory/test_config.py
  - tests/test_factory/test_models.py
  - tests/test_factory/test_cli.py
  - docs/factory/design.md
  - docs/factory/roles.md
  - docs/factory/stages.md
  - docs/factory/artifacts.md
  - .factory/218/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_models.py::test_a_stage_s_second_dispatch_escalates_to_complex
  red_output_sha: see Proof below
  suite: null
docs_cleared: []
---

# Plan: roles.py, the model table, and configs/factory.toml

## Radius

| Path | Why |
| --- | --- |
| `factory/roles.py` | new: `Role`, `ROLES`, `RADIUS`, `role_for`, `scope`, `allowed`, `writable` |
| `factory/config.py` | new: `Config`, `ConfigError`, `CONFIG_PATH`, `load`, `read` |
| `factory/models.py` | `NO_AGENT` becomes a set; `attempt_at_least`; the `[roles]` block and `resolve_role`; `resolve(..., state=None)` |
| `factory/routing.py` | the `Stage` enum only: `spec-review` and `accept`. `ROWS`, `VERDICTS`, `resolve` are untouched |
| `factory/cli.py` | `_model` passes state for a v2 chain, none for v1, and maps `StateError` and `UnknownChainVersion` to exit 3 |
| `factory/AGENTS.md` | one paragraph: the role table and `factory.toml` |
| `configs/factory-models.toml` | the decided stages, `[roles]`, the escalation override |
| `configs/factory.toml` | new, maintainer-owned caps |
| `tests/test_factory/test_roles.py` | new: the table, scopes, `allowed`, `role_for`, the `roles.md` equality |
| `tests/test_factory/test_config.py` | new: `factory.toml` and its errors |
| `tests/test_factory/test_models.py` | new tests for escalation and `[roles]`; two changed tests (below) |
| `tests/test_factory/test_cli.py` | `_model` on v1 and v2 chains; one changed test (below) |
| `docs/factory/design.md` | R9 reversed; sections 2, 5, 6, 8, 10 and 11 |
| `docs/factory/roles.md` | the v2 table; the v1 table kept under its own heading |
| `docs/factory/stages.md`, `docs/factory/artifacts.md` | Supersedes notes name #237 for the routing rows |

`factory/merge.py` (`POLICY`) and `factory/state.py` (`dispatched`, `load`) are
read, not changed. `factory/**` is protected, so this PR is a human merge.
`tests/test_factory/test_routing.py` is not touched and must pass as it is.

## Order of work

1. Write the red tests; run them against the unchanged source; save the `E` lines.
2. `routing.Stage`, then `roles.py`, `config.py`, `models.py`, `cli.py`.
3. The two TOML files.
4. The docs.
5. Full suite, ruff, pyright.

## The three notes from spec review 3, settled

1. **The Shape's Documenter scope is corrected.** The Shape lists `!docs/adr/**`
   and `!docs/agents/typing.md` as literals and omits `park.md`. Do not copy it.
   The Documenter's static writes are `docs/**`, `**/AGENTS.md`, `!.claude/**`,
   `CONTEXT.md`, `.factory/<n>/plan.md` and `.factory/<n>/park.md`; `scope`
   appends, for this role, a `!` exclusion for each pattern read from
   `merge.POLICY`. Nothing is copied from `merge.py`.
2. **The rule: every pattern in `merge.POLICY.hard_stop_paths` and
   `merge.POLICY.protected_paths` is excluded, not only the `docs/` ones.** So
   `**/AGENTS.md` cannot reach `factory/AGENTS.md` (`factory/**` is protected),
   and the exclusion holds as the lists grow. Tested: `AGENTS.md` and
   `docs/AGENTS.md` are writable; `factory/AGENTS.md` and `.claude/AGENTS.md`
   are not; `docs/adr/**`, `docs/agents/typing.md` and
   `docs/factory/merge-policy.md` are not; and a test reads `POLICY` itself, so
   it follows the lists.
3. **The radius lists** `factory/config.py`, `factory/cli.py`,
   `docs/factory/design.md`, the Supersedes notes in `stages.md`, `roles.md` and
   `artifacts.md`, and the rest, above. `worker_timeout_min` and `poll_s` are
   optional keys whose values #159 supplies (not #220, whose herdr adapter has
   only its own internal timeouts).

## Design in brief

- **Write patterns** match with `PurePosixPath.full_match`, as `merge.py` does.
  A path is writable when some positive pattern matches and no `!` pattern
  does: exclusions win whatever their position. `RADIUS` (`"<radius>"`) is a
  positive entry only the Builder has, returned by `scope` unexpanded, for #163.
- **`allowed(role, argv)`** skips the leading global options (tokens starting
  with `-`), then matches an entry as a prefix of the remaining words. `hook` is
  allowed for every role and is in no role's `commands`.
- **`role_for(stage)`**: designer for `design`, spec-reviewer for
  `spec-review`, planner for `build-planning`, builder for
  `build-implementing`, documenter for `document`, reviewer for `review`;
  `None` for `accept`, `integrate`, `qa`, `plan`, `test`. The orchestrator has
  no stage. The v1 roles (Clerk, Specifier, QA Operator, Integrator ...) stay in
  `roles.md` under their own heading, for hand-worked tickets.
- **`attempt_at_least`**: `Override.when` is `Mapping[str, bool | int]`;
  `method_live` must be a bool and `attempt_at_least` an int of at least 2 that
  is not a bool. `resolve(table, stage, chain, state)` computes the attempt as
  `state.dispatched(state, stage).attempt`, or 1 with no state. The state is the
  one before the dispatch is recorded, so a stage's second dispatch is 2.
- **`[roles]`** is optional in a table; `resolve_role(table, role)` gives the
  named tier, `standard` when a stageless role is absent, and `TableError` for a
  name that is not in `ROLES` or a role that has stages (those resolve by stage).
- **`factory.toml`** is read from the session's checkout (`read(session)`).
  `ConfigError` carries `exit_code = NEEDS_HUMAN` and names the key. Nothing
  reads it yet: #159 does. `routing.py` never imports it.
- **`_model`** loads state only when `chain.version == 2` and a ticket is given.

## Decisions I made

- `worker_timeout_min` must be a positive integer, `poll_s` a positive number
  (int or float, never bool), when present. The spec leaves their types open;
  #159 may tighten them.
- `ConfigError`'s exit-3 mapping is a class attribute plus a test of it, because
  no command reads the file yet. Turning it into a returned exit code is #159's.
- The shipped `factory.toml` omits the two optional keys, with a comment.
- `Stage.SPEC_REVIEW` and `Stage.ACCEPT` are inserted in lifecycle order.

## Named changed tests

| Test | Behaviour that moved |
| --- | --- |
| `test_cli.py::test_model_names_the_rule_that_fired` | `qa` moves from standard to complex, so `--stage qa` answers `opus`, `tier=complex`, with the same rule `stage table: qa` |
| `test_models.py::test_the_shipped_table_resolves_every_stage_to_something` (the shipped-table model test) | `accept` joins `integrate` as a stage with no model, so its "has a model" check exempts `NO_AGENT`, not `integrate` alone |
| `test_models.py::test_a_table_key_that_is_not_a_stage_is_a_table_error` | it used `spec-review` as its example of a non-stage; that is now a stage, so it uses `maintain` |

## For the PR body

- Protected path (`factory/**`): a human merges.
- Until #237 lands, `factory model <n>` routes a v2 chain with the v1 rows. No v2
  chain exists before #222.
- #159 must resolve a worker's model before recording its dispatch in
  `state.json`, or the first dispatch of a stage escalates. A test here pins it.
- Nothing here changes which keys reach the game.

## Proof

Filled in after the change.

## Could not verify

Filled in after the change.
