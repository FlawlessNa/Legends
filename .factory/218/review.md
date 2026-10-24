---
ticket: 218
stage: review
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: 9adf5ad5e8a7ff6717a2b52edb6ed518ec41af72
---

# Review: roles.py, the model table, and configs/factory.toml

**Verdict: `pass`.** All 13 criteria in `spec.md` are met. The brief says 14,
but the front matter lists 13; I checked each one.

- **The diff I judged.** `git diff 3b27754..HEAD -- . ':!.factory'`, where
  `3b27754` is the merge of #219. Every touched path is in `plan.md`'s radius.
- **v1 safety.** v1 routing is untouched apart from the two `Stage` members.
- **The red proof.** I re-ran it and it holds. Mutating the behaviour turns
  the named tests red, as listed below.
- **Findings.** Five, all non-blocking. They are notes for #159 and #237 plus
  two wording nits in the docs, and none needs a change before merge.
- **Merge.** `factory/**` is a protected path, so a human merges.

## Criteria

| # | Criterion (short) | Met | Evidence |
| --- | --- | --- | --- |
| 1 | `Stage` gains `spec-review` and `accept`; v1 `ROWS`, `VERDICTS` and `test_routing.py` unchanged | yes | `git diff 3b27754..HEAD -- factory/routing.py` is two `+` lines in the enum, nothing else. `test_routing.py` has no diff. It passes at HEAD, and it passes with the source reverted to `3b27754` (27 passed). |
| 2 | One row per role, with stages, runs-in, writes and commands | yes | `factory/roles.py` `_ROLES` has 7 rows in the documented order. `runs_in` is a `Literal` of the four places. `test_there_is_one_row_per_role...` and `test_each_role_owns_its_stages...` pin it. |
| 3 | Globs are matched like `merge.py` and `!` excludes. The Documenter excludes every POLICY pattern, taken from `merge.py`. `scope` substitutes `<n>` | yes | `permits` uses `PurePosixPath.full_match`. `_policy_exclusions()` reads `POLICY.hard_stop_paths` and `protected_paths`; nothing is copied. Probed directly: `factory/AGENTS.md` False, `docs/adr/x.md` False, `docs/factory/stages.md` True, `docs/factory/merge-policy.md` False, `.claude/AGENTS.md` False, `.factory/218/park.md` True. Plan note 2 picked the broader rule, every pattern. Mutating it to the `docs/`-only rule turns `factory/AGENTS.md` red. |
| 4 | The Builder's scope carries `RADIUS` unexpanded | yes | `scope("builder", 218)` returns `('<radius>', 'tests/**', '.factory/218/plan.md', '.factory/218/park.md')`. `permits` never matches the marker. Only the Builder has it (test). |
| 5 | `allowed` matches the command words after the global options; `hook` is always allowed | yes | `_command_words` drops the leading `-` tokens, then a prefix match. `["--json","spec","submit"]` is allowed for the designer. `hook` is allowed for all 7 roles, with and without `--json`. |
| 6 | `role_for` is None for accept, integrate, qa, plan and test; the v1 roles stay documented | yes | Probed every `Stage` member: `design`→designer, `spec-review`→spec-reviewer, `build-planning`→planner, `build-implementing`→builder, `document`→documenter, `review`→reviewer. `plan`, `accept`, `test`, `qa` and `integrate` give None. `roles.md` keeps "## The v1 roles". |
| 7 | `roles.md` states the v2 table and keeps the v1 table; a test checks the v2 table equals `roles.py` | yes | The equality test is real. Dropping `next` from the Documenter's row in `roles.md` turns `test_roles_md_states_the_v2_table_and_it_equals_roles_py` red. Changing the reviewer's `runs_in` in `roles.py` turns it red too, along with the per-role test. |
| 8 | The model table and `[roles]`: `spec-review` and `qa` complex, `document` standard, `plan` and `test` dropped, fable unavailable; `resolve_role`; `TableError` for a non-role or a staged role; `accept` joins `integrate` with no model | yes | `configs/factory-models.toml` diff. `unavailable = ["fable"]` is kept. `_roles_of` and `resolve_role` both raise for an unknown role and for a role with stages, and each guard has a test that goes red when it is removed. `NO_AGENT = {integrate, accept}`; removing `accept` turns `test_no_model_is_resolved_for_integrate_or_accept` red. |
| 9 | `attempt_at_least` is an int ≥ 2 that rejects bools, read from `dispatched(state, stage).attempt` on the state before the dispatch is recorded | yes | Parametrised rejection of `true`, `1`, `0`, `-3`, `"2"` and `2.0`. I made two mutations of the attempt computation, both described below the table. |
| 10 | `factory model <n>` passes state for v2 and none for v1; a bare `--stage` never escalates | yes | `cli._model` loads state only when `chain.version == 2`. Mutating it to `version in (1, 2)` turns two tests red: `test_a_v1_ticket_never_escalates...` and `test_malformed_state_on_a_v1_chain_is_never_read`. With no ticket, `chain` is None, so there is no state, and `test_the_stage_flag_without_a_ticket_never_escalates` pins that. Malformed state and an unknown chain version both give exit 3. |
| 11 | `factory.toml`: required and optional keys with types; `ConfigError` is exit 3 and names the key; read from the session's checkout; never read by v1 | yes, with finding 1 | `factory/config.py` and 30-odd parametrised tests. Removing the bool guard turns the three `true` cases red. Removing the unknown-key check turns the `attemps` test red. `routing.py` never imports `config`, and `test_a_broken_factory_toml_does_not_touch_factory_model` shows `model` and `next` still return exit 0 with a broken file. |
| 12 | design.md amendments and the Supersedes notes naming #237 | yes, with findings 3 and 4 | R9 is marked "Reversed". §2 adds the flow line and the `document` row between `build-implementing` and `review`. §5 updates the `roles.py` and `models.py` rows. §6 adds the Documenter to the `plan.md` row and the italic "settled by #237" sentence. §8 adds the documenter row. §10 adds the #237 row and the #159 blocker. §11 drops the Document stage. The Supersedes notes in `stages.md`, `roles.md` and `artifacts.md` all name #237. Each item has a docs test. |
| 13 | The changed tests are named; the suite is green | yes | See "Changed tests" below. Full suite: `1 failed, 1744 passed, 3 skipped, 25 deselected`. The one failure is the known flaky #229 test (`test_truncate_lands_exactly_on_the_limit_for_a_multi_step_walk`). It passes 3 of 3 runs alone, and this diff touches nothing under `botting/` or `tests/test_botting/`. |

**The two attempt-computation mutations (criterion 9):**

- **"Recorded first".** I made `resolve` count the dispatch twice. Four
  `test_models` tests and two `test_cli` tests went red, among them
  `test_a_stage_s_first_dispatch_does_not_escalate` and
  `test_a_v2_ticket_with_no_recorded_dispatch_gets_the_standard_model`.
- **"Stale attempt".** I made `resolve` read `state.attempt`. Six tests went
  red, among them `test_a_stage_s_second_dispatch_escalates_to_complex` and the
  CLI next-dispatch and `--stage` tests.

**Escalation by case.** Each case is pinned by a test:

| Case | Expected | Test |
| --- | --- | --- |
| First dispatch | standard | `test_a_stage_s_first_dispatch_does_not_escalate` |
| Second dispatch | complex | `test_a_stage_s_second_dispatch_escalates_to_complex` |
| A new stage | standard | `test_a_new_stage_s_first_dispatch_does_not_escalate` |
| No state | standard | `test_no_state_never_escalates` |

## The red proof, re-run

**1. Revert the source, keep the tests.**

- Files reverted to `3b27754`:
  - `factory/routing.py`, `factory/models.py`, `factory/cli.py`, `factory/AGENTS.md`;
  - `configs/factory-models.toml`;
  - the four docs.
- Files moved aside: `factory/roles.py`, `factory/config.py` and
  `configs/factory.toml`.
- Collection errors, matching `plan.md`'s description:
  - `No module named 'factory.roles'` (test_roles);
  - `No module named 'factory.config'` (test_config, test_cli);
  - `cannot import name 'resolve_role'` (test_models).

`test_routing.py` still passed, 27 tests. As the plan admits, this proves only
that the names were missing, so I did not rely on it.

**2. Behaviour mutations, one at a time, each restored afterwards.** Every one
turned at least one named test red, for the expected reason. One exception is
noted after the list.

- Escalation: "recorded first" and "stale attempt" (6 red each).
- The CLI loads state for v1 (2 red).
- Policy exclusions:
  - the Documenter loses them entirely (5 red);
  - only the `docs/` patterns are excluded (2 red, including `factory/AGENTS.md`).
- `allowed`:
  - the global options are not skipped (10 red);
  - `hook` is dropped from the always-allowed list (14 red).
- Drift between the tables:
  - `roles.md` drifts (1 red);
  - `roles.py` drifts (2 red).
- The model table:
  - the `[roles]` check for a staged role is removed (1 red);
  - the `resolve_role` check for a staged role is removed (1 red);
  - `accept` gets a model (1 red).
- `factory.toml`:
  - a bool cap is accepted (3 red);
  - an unknown key is accepted (1 red).
- `qa` gets a role (1 red).

The exception: removing `isinstance(value, bool)` from the `attempt_at_least`
check turns nothing red. That is correct behaviour, not a gap. TOML's only
booleans are `true` (== 1) and `false` (== 0), and the `< 2` bound already
refuses both. See finding 2.

Afterwards, `git status --short` and `git diff --stat` are empty.

## Changed tests

| Test | Named in plan | Justified |
| --- | --- | --- |
| `test_cli.py::test_model_names_the_rule_that_fired` | yes | `qa` moves to complex, so the record reads `opus  # tier=complex`. The rule string is unchanged. Required by criterion 13. |
| `test_models.py::test_the_shipped_table_resolves_every_stage_to_something` | yes | It exempts `NO_AGENT` instead of `integrate` alone, because `accept` has no model. Required by criterion 13. |
| `test_models.py::test_a_table_key_that_is_not_a_stage_is_a_table_error` | yes (the third, beyond the spec) | Its example of a non-stage, `spec-review`, is now a stage, so it uses `maintain`. The behaviour it pins is unchanged. |

No other existing test changed. `git diff` of the test files shows only those
three edits; everything else is additions.

## Ruff, pyright, suite

- `ruff check` and `ruff format --check` on the 9 changed Python files:
  clean.
- `pyright --pythonpath C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe`
  on the same files: 0 errors, 0 warnings.
- Full suite from the worktree root: green apart from flaky #229, as above.

## Findings

All are non-blocking.

**1. `ConfigError` as exit 3, and "read from the session's checkout", are
contracts with no caller yet.**

- `ConfigError.exit_code = ExitCode.NEEDS_HUMAN` is a class attribute, and a
  test pins it.
- `read(session)` joins `CONFIG_PATH` to whatever root it is given.
- No command reads `factory.toml`, so nothing has yet returned exit 3 or chosen
  the session's root over a ticket worktree.

This matches `plan.md`'s Decisions and Could-not-verify sections, and the spec
puts the reader in #159.

**Fix (for #159):** when `run` loads the config, pass `_session_checkout()`
(not the ticket root), and map `ConfigError` to `exc.exit_code` in the
command's return. Add a CLI-level test for each.

**2. The bool guard in `attempt_at_least` validation is untestable through
TOML.** As described above, the `< 2` bound already refuses `true` and
`false`, so the guard is belt-and-braces. It is harmless and documents intent.

**Fix:** none needed. If kept, a comment saying so would stop a later reader
from expecting a test of it.

**3. design.md §2's "Gone from today's stages" sentence now reads against
itself.** It lists "the Clerk-era `document` of v1" under *Gone*, then says it
"returns as a v2 stage". It is accurate but confusing.

**Fix (any later docs touch):** move `document` out of the *Gone* list, for
example "**Kept, with a new owner:** `document`, now the Documenter's (R9
reversed)."

**4. design.md §11 still gives "R9" as the reason doc lints are deferred.** R9
is now reversed, so the citation points at a ruling that no longer says "no
Document stage". The deferral itself is still right, because the lints are not
on the critical path.

**Fix (any later docs touch):** give the reason in words, for example "not on
the critical path; the Documenter is judged by review".

**5. `allowed` treats every leading `-` token as a valueless global option.**
This is correct today, because the only global option is `--json`
(`cli.py:369`, `store_true`). A future global option that takes a value would
make its value count as the command word. That fails closed, by refusing, so
it is not a hole.

**Fix (for #222, when it enforces the list):** derive the global options from
the parser, or document that global options must stay flags.

**Observation, not a finding.** The Documenter's static writes include
`.factory/<n>/plan.md`, which criterion 3's list does not name. It does not
contradict the criterion. The spec's Shape had it, and design.md §6 now says
the Documenter writes `plan.md` (`docs_cleared` only), so it is consistent.
Narrowing it to the `docs_cleared` key is a hook concern for #163.

## Could not verify

- **No dispatcher exists.** The before-recording obligation on #159 is pinned
  by tests of `resolve` and `factory model`, not by any loop that records
  dispatches.
- **`factory.toml` has no reader.** Exit 3 and the session-root choice are
  unexercised end to end (finding 1).
- **The write scopes and command lists are not enforced** (#163, #222).
  `roles.py` only states them, and I checked them as data and by `permits` and
  `allowed`.
- **Until #237, `factory model <n>` routes a v2 chain with the v1 rows.** That
  is accepted in the spec. The CLI escalation tests exercise it under v1 rows,
  so their expected stage (`build-planning`) depends on v1 routing.
- **GitHub-side items were not checked.** I did not check that #237 exists
  with the carried findings, or #159's blockers. The one exception: I read
  issue #229's title (read-only `gh issue view`) to confirm the failing test
  is the known flaky one.
- **Line endings.** Restoring the reverted files with `git checkout` under
  `core.autocrlf=true` left `models.py`, `routing.py`, `cli.py`, the TOML and
  the docs as CRLF in the working copy. git reports no change, and untouched
  files such as `merge.py` and `state.py` are CRLF too. Their byte-level line
  endings before my run are unknown.
- **Nothing here changes which keys reach the game.** No game client was
  involved, and none is needed.
