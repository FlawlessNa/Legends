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
  red_output_sha: see Proof below
  suite: null
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
