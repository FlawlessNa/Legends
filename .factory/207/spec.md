---
ticket: 207
stage: design
method: suite
criteria:
  - a ticket worktree's base is the nearest ancestor of HEAD among origin/HEAD and the tips of every other issue/* branch, chosen with git merge-base --independent, so a branch stacked on another ticket is judged on its own commits only, with a test on a stacked branch
  - the change set is every path in git diff --name-only <base>...HEAD plus every path git status --porcelain reports, both excluding .factory/, and no branch name appears in any function this ticket adds or changes
  - committing source on a ticket branch with no plan.md and then stopping is refused, where today it is allowed
  - when no base resolves, the change set is the uncommitted paths alone, and the session-start report for that worktree says the committed range is not checked and names the command to fix origin/HEAD, with a test asserting that line
  - every Stop refusal names the worktree, the ticket and the base commit it judged against
  - Stop judges the union of the session's own worktree, when it is on a ticket branch, and every worktree in the session's write log, so a session in worktree A that wrote worktree B by absolute path is judged on both
  - a session on no ticket that wrote nowhere stops cleanly, and a session in worktree A stops cleanly while an unrelated worktree B is mid-build
  - an allowed pre-tool-use write outside .factory/, whose target is a ticket worktree in the same repository as the session, records that worktree under <git-common-dir>/factory/sessions/<session_id>/ as one file per worktree, so concurrent writers cannot lose an entry
  - a session_id that is not a plain token of letters, digits, hyphens and underscores writes no log, and an event with no session_id writes no log
  - the write log can never change the hook's answer, proven by a test that forces every log operation to raise and asserts the deny still prints
  - every test changed in tests/test_factory is named in the plan with the behaviour that moved, decide_stop's signature is unchanged, and the full suite is green
  - docs/factory/stages.md states what Stop sees, marks shell writes into another worktree as [unenforced], and gives git remote set-head origin --auto for a stale origin/HEAD
specified_by: claude
specified_at: 2026-10-22
revised_after: spec-review.md (changes-requested, 10 findings)
---

# Spec: Stop judges the session's own worktree and what it wrote, over everything changed since its base

## Source

Issue #207 as rewritten on 2026-10-22, and `docs/factory/design.md` §3 (d3),
§5 (`hooks.py`) and §13 (B1, B3, X7).

## Shape

- **The base.**
  - The candidates are `origin/HEAD` plus the tip of every local and remote `issue/*` branch other than the worktree's own.
  - Keep the candidates that are ancestors of HEAD. `git merge-base --independent` over them gives the nearest. For several independent ones, take the one with the most commits in common with HEAD (`git rev-list --count`).
  - A stacked ticket is therefore judged against its parent ticket's tip, never against the default branch, where the parent's source would be swept in (spec-review finding 1, reproduced: 12 paths from #216 and #217).
  - No candidate means no base.
- **The change set** is `diff --name-only <base>...HEAD` ∪ `status --porcelain`, excluding `.factory/`.
- **Who is judged** is own ∪ logged.
  - That is the session's own worktree (resolved from the event's `cwd`, #216) when it is on a ticket branch, plus every ticket worktree in the session's write log that still exists.
  - This departs from the issue's "own worktree only". Own-only would drop edit-tool writes that Stop catches today: a ticket session writing B by absolute path, a session that wrote B and then `cd`'d away, and the primary checkout on a ticket branch.
  - It still ends the everyone-blocks-everyone failure (B3), because unrelated worktrees are never judged.
- **The write log.**
  - It is written **after an allowed decision only**, for targets outside `.factory/`, whose governing worktree is on a ticket branch and in the same repository as the session (`decide_write` row 3's identity check).
  - Each entry is a file at `<common>/factory/sessions/<session_id>/<sha1 of the resolved root>`, holding the root's path. Creating a file is atomic per entry, so concurrent hooks cannot lose one. The review measured 26–27% of lines lost with shared-file appends.
  - `session_id` must match `^[A-Za-z0-9_-]{1,128}$`.
  - Every log operation runs inside a `try/except Exception` that discards the error, **after** the decision has been made. The log cannot change the answer, and the hook cannot fail open because of it.
- **Reporting.**
  - Refusals name the worktree, the ticket and the base commit.
  - When no base resolves, the session-start report for that worktree carries one line: the committed range is not checked; run `git remote set-head origin --auto`. That is the channel, because a Stop that allows prints nothing (finding 2).

## Verification method: suite

**Red tests.** They use real temporary git repositories, which `tests/test_factory` has not needed before.
- committed source with no plan, refused;
- a stacked branch judged on its own commits;
- own ∪ logged: A writing B, refused;
- unrelated B mid-build, quiet;
- an off-ticket session that wrote nowhere, quiet;
- one file per root under concurrent writers;
- an invalid `session_id` and a missing one;
- the forced-raise log test;
- the no-base session-start line;
- the base named in the refusal.

**Changed tests,** named in the plan because they assert "every worktree is judged", which this removes (B3):
- the four `_stop_everywhere` tests in `test_cli.py`;
- #216's three `cwd` tests.

These are exactly the seven that patch `_source_changed` or call `_stop_everywhere`. `test_hooks.py`'s `decide_stop` tests stay unchanged, because its signature does not change.

## Decisions I made

- **The hooks read `base...HEAD` again, although B1 rejected it.** B1 rejected it for the *factory loop's* role-scope rules, where a branch accumulates other roles' files. Here it is the hand-worked Stop gate, judging one ticket's source as a whole, which is what B1's own fix keeps on `base...HEAD`.
- **Logs are never deleted here.** They are a handful of tiny files per session. #210 does not cover them; its PR, or a later housekeeping ticket, adds `sessions/` pruning. This is noted on #210.
- **`has_proof` stays "any `proof.suite`"** (chain.py). The loop's `proof.md` (#145) replaces it.
- **The harness is assumed.** That events carry `session_id` and `cwd`, and that a subagent's tool calls carry its own `session_id`, is assumed, not verified. It goes under Could not verify.

## Not in scope

- The factory loop's own judgement of turns (#159).
- Role scopes (#163).
