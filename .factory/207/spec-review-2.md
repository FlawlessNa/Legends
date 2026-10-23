---
ticket: 207
stage: design
cycle: 2
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "a ticket worktree's base is the nearest ancestor of HEAD among origin/HEAD and the tips of every other issue/* branch, chosen with git merge-base --independent, so a branch stacked on another ticket is judged on its own commits only, with a test on a stacked branch"
---

# Spec review, cycle 2: Stop judges the session's own worktree and what it wrote

**Verdict: `changes-requested`, for criterion 1 alone.** I checked only the ten
findings from `spec-review.md`, against `spec.md` at `7b1adbd`.

- **Nine are resolved** at the level of the criteria: 2 to 10.
- **Finding 1 is not.** The new base rule fixes the stacked case, but breaks the
  ordinary case. I reproduced three failures, and in each, committed source
  escapes the gate. That is defect 1 of the issue. Part of the fault is mine: the
  rule follows cycle 1's suggestion, and that suggestion had the second and third
  holes.
- **Five notes remain** for the plan. None changes what a criterion requires.

## 1. The base: three holes, all reproduced (blocking)

I built a scratch repository with `python -I -B` and git 2.39.1: an upstream on
`dev`, a clone, and `issue/1-x` with an artifacts commit and then a `src.py`
commit.

**a. `origin/HEAD` is dropped as soon as `dev` moves.** The Shape keeps "the
candidates that are ancestors of HEAD", and `origin/HEAD` is listed among them
*as itself*. After one upstream commit and a fetch:

```
git merge-base --is-ancestor origin/HEAD HEAD   -> false (dropped)
```

An unstacked ticket then has no candidate. The rule then gives:

- no base;
- an uncommitted-only change set;
- committed `src.py` invisible;
- a session-start line telling the user to run `set-head`, which fixes nothing.

This is the common case: any ticket open while anything else merges.

**Fix:** the candidate is `git merge-base HEAD origin/HEAD`, not `origin/HEAD`.
That was cycle 1's wording. The revision lost it.

**b. The pushed copy of your own branch becomes your base.** I pushed `issue/1-x`
and made one more local commit. Then:

```
git for-each-ref --merged HEAD 'refs/heads/issue/*' 'refs/remotes/origin/issue/*'
  refs/heads/issue/1-x
  refs/remotes/origin/issue/1-x
```

"Other than the worktree's own" excludes only the local ref. If the remote copy
is a candidate, the base is the pushed tip, and only unpushed commits are judged.
Every source commit that was pushed escapes.

**Fix:** exclude every candidate whose branch names the same ticket number
(`ticket_from_branch`), whether local or remote.

**c. A child branch with no commits of its own becomes your base.** I created
`issue/2-child` at `HEAD~1`, the kind of branch stacked on yours that has not
started yet. Then:

```
independent base = 24a5e9c src      ->  change set: src2.py   (src.py escapes)
```

A tip cannot tell a parent from a child that has made no commits yet. Both are
just an ancestor commit of HEAD.

**Fix (one option; the planner may choose another, but the spec must name it):**
anchor the base on this ticket's own first commit. Bootstrap rule 1 makes the
first commit the one that adds `.factory/<n>/`. Keep only the candidates that are
ancestors of that commit's **parent**. A parent ticket's tip is such an ancestor.
A child cut at or after the first commit is not, including one cut exactly at it.
When no such commit exists, fall back to `merge-base HEAD origin/HEAD` alone.

**Required tests,** each red against the cycle-2 rule:

- an unstacked ticket after `dev` has moved: its committed source is still seen;
- after pushing: its pushed commits are still seen;
- with a child branch cut inside it: its earlier commits are still seen.

They sit alongside the stacked-branch test the spec already has.

## 2 to 10: resolved

| # | Finding | How it is resolved |
| --- | --- | --- |
| 2 | No channel for "not checked" | Criterion 4: the session-start report for that worktree, with a test asserting the line. |
| 3 | The log loses entries; it can fail open; `session_id` unchecked | Criterion 8: one file per worktree. Criterion 10: a forced-raise test proves the deny still prints. Criterion 9: `session_id` is validated, and absent means no log. |
| 4 | Whose common dir | Criterion 8: same repository as the session, under `<git-common-dir>/factory/sessions/<session_id>/`. |
| 5 | Edit-tool writes dropped by the scope | Criterion 6: own ∪ logged, recorded as a departure from the issue, with reasons. |
| 6 | Stale `origin/HEAD` | Criterion 5: every refusal names the base commit. Criterion 12: `set-head --auto`. |
| 7 | Over-logging | Criterion 8: allowed writes only, outside `.factory/`. |
| 8 | Changed tests | Criterion 11: the seven tests named, `decide_stop`'s signature unchanged, real git repos noted. |
| 9 | "No branch name" | Criterion 2: scoped to the functions this ticket adds or changes. |
| 10 | B1 and pruning | B1 is answered in Decisions. The pruning comment is on #210; I read it, without writing to GitHub. |

## Notes for the plan

**a. The digest's spelling (finding 3).** On Windows, `resolve()` can return
different case for the same root. #217's review saw a lower-case drive segment.
A SHA-1 of the raw string then gives two files for one worktree. That is harmless
to judging, but it breaks criterion 8's "one file per worktree". **The plan
must:**

- hash `os.path.normcase(str(root))`;
- deduplicate by `Path` when reading the log.

**b. The moved-`cwd` residual (finding 4).** The log is read through the
session's root at Stop time, from the event's `cwd`. If the session has `cd`'d
outside the repository, the log is not found and nothing is judged. That is no
worse than today. Cycle 1 asked for it to be named or covered, and the spec does
neither. **The plan must:** list it under *Could not verify*, or fall back to
`CLAUDE_PROJECT_DIR`.

**c. The primary checkout on a ticket branch (finding 5).** Own ∪ logged covers
it. The red tests include "A writing B" but not this case. **The plan should:**
add the primary on a ticket branch writing B.

**d. The remote's name (finding 6).** The rule assumes a remote named `origin`.
**The plan should:** say so in a Decision.

**e. Where the no-base line is computed (finding 8).** `session_report` lives in
`hooks.py`, which spawns no git, and every test of it calls
`session_report(repo, branch)` with a hand-faked `.git`. **The plan should:**

- compute the base in `cli.py` and pass the line in, through an optional
  parameter or by appending it;
- name every `test_hooks.py` test that changes as a result.

The existing assertions are substrings or exact line lists *off* a ticket branch,
so none should move. The plan should confirm this rather than assume it.

## What this review could not verify

- I did not run pytest.
- **The anchored rule in 1c is untested.** I reproduced the three holes, not the
  fix.
- **The harness assumptions stand as in cycle 1**:
  - `session_id` and `cwd` in events;
  - subagent `session_id`s;
  - Stop firing only for main sessions.
