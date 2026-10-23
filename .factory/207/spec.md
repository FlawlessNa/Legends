---
ticket: 207
stage: design
method: suite
criteria:
  - a ticket worktree's change set is every path in git diff --name-only <base>...HEAD plus every path git status --porcelain reports, both excluding .factory/, where <base> is git merge-base HEAD origin/HEAD and no branch name appears in the code
  - committing source on a ticket branch with no plan.md and then stopping is refused, where today it is allowed
  - when the base cannot be resolved (no origin/HEAD, or no merge-base), the change set is the uncommitted paths alone, and the refusal or report says the committed range was not checked
  - a session whose own worktree is on a ticket branch is judged on that worktree alone, so it stops cleanly while another ticket worktree is mid-build
  - a pre-tool-use event carrying a session_id appends the target's governing worktree root to <git-common-dir>/factory/sessions/<session_id> when that worktree is on a ticket branch, as a plain file append with no subprocess, once per distinct root
  - a session on no ticket is judged on exactly the ticket worktrees its log names, so a session that wrote into worktree B by absolute path is refused while B is incomplete, and one that wrote nowhere stops cleanly
  - an event with no session_id writes no log, and an off-ticket session with no log is judged on nothing, which is documented as the residual for shell writes into another worktree
  - Stop's refusal text names the worktree and the ticket judged
  - every test changed in tests/test_factory is named in the plan with the behaviour that moved, and the full suite is green
  - docs/factory/stages.md states what Stop sees (the session's own worktree since its base, or the worktrees an off-ticket session wrote into) and marks shell writes into another worktree by an off-ticket session as [unenforced]
specified_by: claude
specified_at: 2026-10-22
---

# Spec: Stop judges the session's own worktree, over everything changed since its base

## Source

Issue #207 as rewritten on 2026-10-22, and `docs/factory/design.md` §3 (d3),
§5 (`hooks.py`) and §13 (B3, X7).

## Shape

- **The change set.** `_source_changed(root)` becomes "changed since base".
  - It runs `git merge-base HEAD origin/HEAD`. `origin/HEAD` is the remote's default branch: `refs/remotes/origin/dev` here, verified.
  - Then `git diff --name-only <base>...HEAD` and `git status --porcelain`, taking the union.
  - It ignores `.factory/` as today.
  - When the base is unresolvable, the committed range is skipped, and the decision says so.
- **Who is judged.** `_stop_everywhere` is replaced by a scope rule:
  - The session's root is already resolved from the event's `cwd` (#216). If that worktree is on a ticket branch, judge it alone.
  - Otherwise read `<git-common-dir>/factory/sessions/<session_id>` and judge each ticket worktree it names that still exists.
  - With no `session_id`, or no log, judge nothing.
- **The write log.** The pre-tool-use hook, after deciding, appends the target's governing root when that root is on a ticket branch and the event carries a `session_id`.
  - It writes one line per distinct root: it reads the small file first and skips duplicates.
  - The log is written whatever the decision, because a refused write leaves nothing to judge, but an allowed one does.
  - The directory is created on first use, and every OS error is swallowed. A hook that throws blocks every edit.

## Verification method: suite

**Red tests:**
- committed source with no plan, refused;
- a session in worktree A, quiet while B is mid-build;
- an off-ticket session that wrote into B, refused;
- an off-ticket session that wrote nowhere, quiet;
- the log is appended once per root, and nothing is logged without a `session_id`;
- the unresolvable base is reported.

Each is red today, except "wrote into B, refused", which is green today because everything is judged. It must stay green.

**Tests that change, because the behaviour moved (B3).** They assert "every worktree is judged", which this ticket removes. Each is rewritten to set up the session's log, or the session's own worktree, and is named in the plan:
- `test_the_stop_gate_refuses_for_a_worktree_the_session_is_not_in`
- `test_the_stop_gate_is_quiet_when_every_worktree_has_its_proof`
- `test_the_stop_gate_runs_git_in_each_worktree_not_in_the_session`
- `test_the_stop_hook_is_wired_to_the_fold_not_to_one_worktree`
- #216's `test_the_stop_hook_takes_the_session_from_the_event_s_cwd`, `test_a_cwd_naming_no_directory_falls_back_to_the_process_cwd` and `test_a_cwd_inside_a_worktree_is_judged_from_the_worktree_root`

## Decisions I made

- **The base is the merge-base with `origin/HEAD`, not the upstream.** A ticket branch's upstream is itself (`origin/issue/<n>-*`) once pushed. `origin/HEAD` follows the repository's default branch, consistent with #217.
- **Logs are never deleted.** There is one small file per session, and a session spans many turns. Pruning belongs with #210's housekeeping.
- **`has_proof` stays "any `proof.suite`"** (chain.py). The loop's `proof.md` (#145) replaces it. This is noted in the PR body, not fixed here.

## Not in scope

- The factory loop's own judgement of turns (#159).
- Role scopes (#163).
