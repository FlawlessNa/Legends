---
ticket: 207
stage: build
radius:
  - factory/cli.py
  - factory/worktrees.py
  - factory/AGENTS.md
  - tests/test_factory/test_stop_scope.py
  - tests/test_factory/test_cli.py
  - docs/factory/stages.md
  - docs/factory/design.md
  - .factory/207/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_stop_scope.py::test_committed_source_with_no_plan_is_refused
  red_output_sha: 0e144e80c055
  suite: pass
docs_cleared: []
---

# Plan: Stop judges the session's own worktree and what it wrote, since its base

## Radius

| Path | Why |
| --- | --- |
| `factory/cli.py` | `_base`, `_changed_paths`; `_source_changed` reads them; `_stop_everywhere` judges own and logged worktrees and names worktree, ticket and base; `_run_hook` logs after an allowed write and adds the no-base line at session start |
| `factory/worktrees.py` | the write log: `log_write`, `logged_worktrees`, the `session_id` pattern. Still runs no git |
| `factory/AGENTS.md` | the `stop` row of the hooks table |
| `tests/test_factory/test_stop_scope.py` | new: the red tests, on real temporary git repositories |
| `tests/test_factory/test_cli.py` | the seven named changed tests below |
| `docs/factory/stages.md` | what Stop sees; shell writes into another worktree `[unenforced]`; `git remote set-head origin --auto` |
| `docs/factory/design.md` | d3 said Stop "judges every ticket worktree"; made true |

`factory/hooks.py` is **not** in the radius: `decide_stop` keeps its signature and
`decide_write` is used as it is. `factory/**` is protected, so this PR is a human
merge.

## Order of work

1. Write the red tests; run them against the unchanged source; save the `E` lines.
2. `worktrees.py` (the log), then `cli.py` (base, change set, Stop, session start).
3. Change the seven named tests.
4. `stages.md`, `design.md`, `AGENTS.md`.
5. Full suite, ruff, pyright.

## The three notes from the passing spec review (cycle 3), settled

1. **Merging `dev` into a ticket branch.** The base is the *later* of `f^` (the
   chain commit's parent) and `git merge-base HEAD origin/HEAD`, when one is an
   ancestor of the other (`git merge-base --is-ancestor`); otherwise `f^`. Red
   test: a real `git merge` of an advanced `dev`; `dev`'s paths are not in the
   change set. The stacked, dev-moved, pushed and child cases keep `f^`, because
   the merge-base is `f^` or older there, and each has a test that must stay green.
2. **A chain commit with no parent.** `f^` does not resolve, so the base is
   `merge-base HEAD origin/HEAD`, and if that fails too, no base: the change set
   is the uncommitted paths alone and session start says so. Tests: a root chain
   commit with `origin/HEAD` on it (base is that commit), and with no `origin`
   (no base, committed source unseen).
3. **A chain that already sits on `dev`** (a reopened ticket, or intent committed
   before branching). `f^` is then on the default branch's history, so it is an
   ancestor of the merge-base and note 1's rule picks the merge-base. Test: a
   chain committed on `dev` itself, then a branch with source; only the branch's
   source counts.

## Named changed tests

All seven patch `_source_changed` or call `_stop_everywhere`, and asserted that
every ticket worktree is judged, which is the behaviour B3 removes.

| Test (test_cli.py) | Behaviour that moved |
| --- | --- |
| `test_the_stop_gate_refuses_for_a_worktree_the_session_is_not_in` | the worktree is refused only because the session's write log names it |
| `test_the_stop_gate_is_quiet_when_every_worktree_has_its_proof` | logged, so it is in scope; still quiet because proven |
| `test_the_stop_gate_runs_git_in_each_worktree_not_in_the_session` | git still runs per judged worktree; the worktree is judged because it is logged |
| `test_the_stop_hook_is_wired_to_the_fold_not_to_one_worktree` | the event carries a `session_id` whose log names the worktree |
| `test_the_stop_hook_takes_the_session_from_the_event_s_cwd` | same |
| `test_a_cwd_naming_no_directory_falls_back_to_the_process_cwd` | same |
| `test_a_cwd_inside_a_worktree_is_judged_from_the_worktree_root` | same |

Each gains a `session_id` and a log entry written through `log_write`. Any other
test changed is added here with its reason.

## Decisions I made

- `_base` and `_changed_paths` live in `cli.py` beside `_source_changed`, not in
  `hooks.py`, which runs no git. The refusal text is `decide_stop`'s reason plus
  one line added in `cli.py`, so `decide_stop` is untouched.
- The write log is found through the session's repository (`<git-common-dir>`),
  so a session that left the repository altogether loses its log as well as its
  own-worktree scope. The spec says only the latter; a session that moved between
  worktrees of the same repository keeps both.
- A git failure (no git, timeout) leaves the change set empty, as `_source_changed`
  does today.

## For the PR body

- Protected path (`factory/**`): a human merges.
- Who is judged changed: unrelated worktrees mid-build no longer block anyone.

## Proof

**Red, before the change.** `tests/test_factory/test_stop_scope.py` was run against the unchanged source: 26 failed, 13 passed (the 13 are guards that must stay green: a proven ticket stops cleanly, an invalid `session_id` writes nothing, a refused write is not logged, a vanished logged worktree is skipped, and similar). The `E` lines are in the scratchpad file `red207.txt` (sha256 prefix `0e144e80c055`). The reasons:

```
E   AttributeError: module 'factory.cli' has no attribute '_base'            (nine tests: no base is computed)
E   AttributeError: module 'factory.cli' has no attribute '_changed_paths'   (no committed range is read)
E   AttributeError: ... factory.cli has no attribute 'log_write'            (no write log; forced-raise test)
E   assert not True  where Decision(allowed=True) = _stop_everywhere(wt)     (committed source with no plan allowed)
E   assert '<worktree>' in ''                                               (a refusal does not name worktree, ticket, base)
E   KeyError: 'decision'                                                    (a session that wrote B is not stopped for B)
E   assert False  where is_dir() ...sessions/s1                             (no log written after an allowed write)
E   assert 'not checked' in '<session-start report>'                         (no no-base line)
```

Two further tests are red only because Stop used to judge every worktree: an unrelated worktree mid-build blocked a session in worktree A, and blocked a session on no ticket.

`test_the_default_branch_merged_in_is_not_the_ticket_s_source` and `test_a_chain_that_already_sits_on_the_default_branch` also fail when the later-of rule in `_base` is disabled (checked by hand: `if False and _is_ancestor(...)`; both red, restored), so they pin note 1 and note 3 and not merely the attribute's existence.

**Green, after.** `pytest` from the worktree root: `1279 passed, 3 skipped, 25 deselected`, 0 failed, 0 errors, 0 xfailed. `ruff check`, `ruff format` and `pyright` are clean on the changed Python files, and pre-commit passed on `8c3a717`.

**Named changed tests**, all seven as listed above: each now passes a `session_id` and has the worktree in that session's log (written by hand with `_logged`, because those fixtures give every worktree its own `.git` directory, which the identity rule reads as a separate repository). Nothing else was edited; `test_ticket_worktrees_is_the_same_function_the_cli_exports` still passes through a re-export in `cli.py`.

## Could not verify

- **The harness.** That every event carries `session_id` and `cwd`, and that a subagent's tool calls carry their own `session_id`, is assumed. Nothing here ran a live Claude Code session.
- **A session that leaves the repository** before Stop loses its write log as well as its own-worktree scope, because the log lives under the repository's git directory and the repository is found from the session's `cwd`. The spec said only the scope would be lost. A session that only moves between worktrees of the same repository keeps both.
- **Real `origin/HEAD`.** The tests simulate it with `update-ref` and `symbolic-ref`; no test ran against a fetched remote. The `no base` and `merge-base` paths are exercised on those refs only.
- **A shallow boundary** is not tested directly (a root commit stands in for it); `git rev-parse <f>^` fails the same way for both.
- **Windows case and 8.3 names** in the log: entries are keyed by the case-normalised resolved root and deduplicated by resolved `Path`, but no test makes two spellings of one path.
- **Hook cost.** Stop now runs about five git processes per judged worktree; the review measured the history walk at 0.1 to 0.15 s here, and nothing was measured on a slower disk.
- **Log pruning.** Session logs are never deleted (spec decision); #210 or a later ticket owns that.
- **The red tests were committed together with the change**, not before it: pre-commit's pyright refuses a test file that names `cli._base` before it exists, and hooks were not skipped. The red run is the scratchpad file above.
- The flaky `test_truncate_lands_exactly_on_the_limit_for_a_multi_step_walk` (#229) did not fail in the final run.
