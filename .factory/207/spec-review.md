---
ticket: 207
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "a ticket worktree's change set is every path in git diff --name-only <base>...HEAD plus every path git status --porcelain reports, both excluding .factory/, where <base> is git merge-base HEAD origin/HEAD and no branch name appears in the code"
---

# Spec review: Stop judges the session's own worktree, over everything changed since its base

**Verdict: `changes-requested`.** I reviewed `spec.md` at `987af4e` against
`intent.md`, issue #207, `docs/factory/design.md` §3, §5 and §13 (B1, B3, X7), and
the code on this branch. The overall shape is right: the change set is "since
base", the scope is per session, and the write log replaces "every worktree".
The criteria cover the issue's four acceptance cases.

Three findings must change before planning:

- **Finding 1.** Criterion 1's base breaks every stacked ticket, including this one.
- **Finding 2.** Criterion 3 names a "report" that has no channel.
- **Finding 3.** The write log as specified loses entries on Windows, and a log
  failure can turn a deny into an allow.

Findings 4 to 6 are gaps the spec must decide explicitly. Findings 7 to 10 are
minor.

## 1. Stacked tickets: `merge-base HEAD origin/HEAD` counts the parent ticket's source (blocking)

**Evidence.** This worktree is the case. Its branch is stacked on
`issue/217-protect-and-base`, which is stacked on #216. Run here:

```
git merge-base HEAD origin/HEAD             -> 9654223 (dev's tip)
git diff --name-only 9654223...HEAD | grep -v '^\.factory/'
  .claude/hooks/factory-hook.sh  .gitattributes  docs/factory/design.md
  docs/factory/merge-policy.md   factory/AGENTS.md  factory/cli.py
  factory/merge.py  factory/worktrees.py  tests/test_factory/test_cli.py
  tests/test_factory/test_hook_wiring.py  tests/test_factory/test_merge.py
  tests/test_factory/test_worktrees.py
```

That is 12 source paths, none of them #207's. Ticket 207 has no `plan.md`. So
under criterion 1, `decide_stop` refuses every turn of every main session in
this worktree:

- the specifier who wrote this spec;
- this review stage;
- the planner;
- any off-ticket orchestrator that logged a write here, even a `.factory/` one.

The refusal lasts from the branch's creation until `plan.md` carries a proof. The
only way out is `FACTORY_HOOKS=off`, and `decide_stop`'s own docstring warns
against teaching that. The issue asks for "the branch the ticket was cut from".
For a stacked ticket that branch is the parent ticket, not `origin/HEAD`. The
spec's decision covers the upstream alternative but never mentions stacking,
although three tickets in flight are stacked right now.

**Fix.** Add a criterion and a red test for a stacked ticket: a branch cut from
another ticket branch, with the parent's source committed and none of its own, is
quiet at Stop. One rule that does this with two git processes, and names no
branch:

1. Collect the candidates:
   - `git merge-base HEAD origin/HEAD`;
   - the tips of the other `refs/heads/issue/*` and `refs/remotes/origin/issue/*`
     branches that are ancestors of HEAD (`git for-each-ref --merged HEAD`);
   - not HEAD's own branch.
2. Take `git merge-base --independent` over the candidates. A single survivor is
   the base.

The planner may choose another rule, but the spec must name one. If the
maintainer would rather accept the refusal, the spec must say so as a decision
and mark it in `stages.md`. As written, the spec says neither.

## 2. Criterion 3's "report" has no channel (blocking: not decidable)

**Evidence.** Today Stop can say one thing: `{"decision": "block", "reason": ...}`
(`cli.py:394-396`). Take an unresolvable base with a clean working tree. The
decision is allow, `_run_hook` writes nothing, and there is nowhere for "the
committed range was not checked" to appear. So "the refusal or report says"
cannot be tested in the allow case, and that is the case that matters. The
silent weakening happens exactly when nothing is refused.

**Fix.** Name the channel and make the criterion assert it. For example: "when the
base is unresolvable and Stop allows, the hook's JSON carries a `systemMessage`
saying the committed range was not checked; when it refuses, the `reason` says
so". `systemMessage` on a Stop hook is an assumption about the harness. Record it
as one. If it cannot be relied on, use the `SessionStart` report instead, and
state that.

## 3. The write log: lost entries on Windows, and a failure that becomes an allow (blocking)

**a. Concurrent appends lose lines on Windows.** I measured it with `python -I -B`:
8 processes, each appending 400 lines with `open(path, "a")`.

| Run | Lines written | Lines on disk | Lost |
| --- | --- | --- | --- |
| 1 | 3200 | 2319 | 27% |
| 2 | 3200 | 2381 | 26% |

Every surviving line was well formed. The losses were whole overwrites, because
the CRT emulates `O_APPEND` by seeking and then writing, and the two steps are
not atomic.

The spec's "reads the small file first and skips duplicates" makes it worse. Two
parallel `PreToolUse` hooks from one session, with parallel Edit calls into
worktrees B and C, both read and both append, and one entry can vanish. A lost
entry means a worktree the session wrote is not judged. That is #206's hole,
reopened by a race.

**b. A log failure can lose a deny.** The spec swallows "every OS error". A
`UnicodeEncodeError` is not an `OSError`: it is a `ValueError` subclass, raised
by a lone surrogate in a path. A `ValueError` from a NUL byte is not one either.
If the log runs "after deciding" but before `_run_hook` writes the payload, such
an error crashes the hook with a non-zero exit. The harness treats that as
non-blocking, so a refused write goes through.

**c. `session_id` becomes a path component unchecked.** A `/` or `..` in it
moves the write.

**Fix.**

- Replace the appended file with a per-session directory holding **one file per
  root**: `<common>/factory/sessions/<session_id>/<digest of the resolved root>`,
  with the root's path as the content. Creating a file is atomic per entry, needs
  no read-before-write, and cannot lose a sibling entry.
- Change "once per distinct root" to "each root at least once; Stop deduplicates
  by `Path`".
- Require that the log can never change the hook's answer. Either emit the
  payload first, or swallow `Exception` around the log. Add a test that forces
  the log write to raise and asserts the deny still comes out.
- Accept a `session_id` only if it matches `[A-Za-z0-9_-]{1,128}`. Otherwise
  write no log, as for a missing one.

## 4. Whose `<git-common-dir>` is unspecified

**Evidence.** Criterion 5 says `<git-common-dir>/factory/sessions/<session_id>`
but not whose common dir. If it is the target's, then a write into *another
repository's* checkout that happens to be on an `issue/*` branch puts a file in
that repository's `.git`. `decide_write` row 3 refuses to judge another
repository for the same reason (`hooks.py:177-184`, `_common`). Stop reads the
log through the session's root at Stop time. A session that has `cd`'d out of
the repository (the event's `cwd` follows the shell) finds no common dir and
judges nothing. That is no worse than today, where `ticket_worktrees` of a
non-repository is `()`, but nothing records it.

**Fix.** The criterion should say:

- log only when `_common(target root) == _common(session root)`;
- write under that common dir, found with `_common`, which needs no subprocess;
- add a test with a foreign repository on an `issue/*` branch: no file written
  there.

Name the moved-`cwd` case as a residual, or fall back to `CLAUDE_PROJECT_DIR`'s
common dir when the session root is in no repository.

## 5. The scope rule drops edit-tool writes by on-ticket sessions, and the primary on a ticket branch

**Evidence.** The spec logs every session's writes, but reads the log only when
the session's root is off-ticket. Three cases follow.

- **A session in ticket worktree A writes B by absolute path** (an allowed write:
  B has spec and review). Its Stop judges A alone. Today `_stop_everywhere`
  refuses it while B has source and no proof. This is the edit-tool gap you
  asked me to look for. It is a silent regression from today, and no existing
  test pins it.
- **A session that starts in the primary, writes B, then `cd`s into A** is
  judged on A alone. B is dropped.
- **The session's root is the primary checkout on a ticket branch** (asked
  directly). The spec judges the primary alone and ignores the log. Its change
  set is the maintainer's working tree. Right now that includes the primary's
  modified `.gitignore`, which counts as source because only `.factory/` is
  excluded. Meanwhile any worktree the session wrote into goes unjudged. #209
  treats the primary as the seat "where no ticket governs anything" and consults
  no branch, and this rule consults one.

**Fix.** Judge `{own root, if it is on a ticket branch} ∪ {logged roots still on
a ticket branch in this repository}`, deduplicated by `Path`. This still
satisfies every acceptance case. A stays quiet while B is mid-build, because B is
not logged. It also closes all three cases above, and it matches X7's intent:
"S3 silently reverted #206". It departs from the issue's literal "its own
worktree only", so the spec must say so as a decision. Add tests for:

- the ticket session that wrote B;
- the primary on a ticket branch that wrote B.

If the spec keeps its rule instead, it must record the regression as a decision,
pin it with a test, and mark it `[unenforced]` in `stages.md`. Either way,
criterion 10's residual list must also cover:

- shell writes into another worktree by an **on-ticket** session;
- the unresolvable-base fallback.

## 6. A stale `origin/HEAD` silently moves the base

**Evidence.** `git fetch` never updates `refs/remotes/origin/HEAD`. I checked
with git 2.39.1 in a scratch clone: after the remote's HEAD moved from `main` to
`dev` and a fetch, the local `origin/HEAD` still read `refs/remotes/origin/main`
while `ls-remote` said `dev`. "Verified `refs/remotes/origin/dev` here" is true of
this machine only. A clone made before 2026-10-22 points at
`origin/movements-improvements`. That branch is identical to `origin/dev` today
(`rev-list` counts 0 both ways), but the base drifts back as `dev` moves, and
every ticket is then refused for `dev`'s own commits.

What I checked and found sound:

- **A linked worktree.** Refs are shared, and the base resolved correctly here.
- **A shallow clone.** Once history no longer meets, `merge-base` exits 1 with no
  output. A clone without `origin/HEAD` exits 128. Both fall into criterion 3's
  fallback, which is correct.

**Fix.**

- The refusal text names the base it used, as ref and short SHA, so a wrong base
  can be diagnosed.
- `stages.md` gives `git remote set-head origin --auto` as the repair.
- The spec states that the remote is assumed to be named `origin`.

## 7. Logging refused writes and `.factory/` writes binds a session to work it does not owe (minor)

The spec's reason contradicts its rule: "The log is written whatever the
decision, because a refused write leaves nothing to judge, but an allowed one
does." A refused write changed nothing in B, but once logged, the session is held
to B's whole change set for the rest of the session. The same goes for a
`.factory/` write. `IN_PRIMARY` tells the orchestrator to write the artifacts
*in* the ticket worktree, so the orchestrator would then be refused whenever any
other session's Builder has unproven source in B. **Fix:** log only allowed
writes, outside the target root's `.factory/`, which is exactly what the change
set excludes.

## 8. The changed-test list (minor)

The seven named tests are exactly the ones in `test_cli.py` that call
`_stop_everywhere` or patch `_source_changed`: lines 338, 364, 380, 398, 522, 547
and 595. The list is complete for that file, and each change is justified,
because each depends on "every worktree is judged". Two things are missing:

- **The `decide_stop` tests in `test_hooks.py`** (lines 138 and 215-246). They
  are untouched only if `decide_stop`'s signature stays the same. Criterion 3's
  note might be threaded through it. The spec should say the signature is
  unchanged, or name those tests.
- **Real git in the new tests.** Every existing Stop test fakes `.git` by hand
  (`_wt`). The new red tests for criteria 1-3 need a real repository with
  `refs/remotes/origin/HEAD` and a real `git` binary, which `tests/test_factory`
  has never needed. The plan should say so.

`test_hook_wiring.py`'s Stop case asserts only the exit code, and runs the
installed code, so it is unaffected.

## 9. "No branch name appears in the code" is not checkable as worded (minor)

`hooks.py:504` already names `movements-improvements` in a docstring. **Fix:**
scope the check to the functions this ticket adds or changes: no string literal
equal to a branch name.

## 10. Unacknowledged ledger items (minor)

- **Pruning.** The spec says pruning "belongs with #210". I read #210's body: it
  covers merged worktrees and branches, not session logs. Either comment on #210
  or open a follow-up, and name unbounded growth as a residual.
- **B1.** Design §13 B1 is "Stop over `base...HEAD` refuses later workers", taken
  by moving judgement to the loop. This ticket reintroduces `base...HEAD` in the
  hook, as the issue asks. The spec should say why that is acceptable under v1: a
  later worker inherits a `plan.md` with a proof. Finding 1 is the case where it
  is not acceptable.

## What this review could not verify

- I did not run pytest.
- **What a hook event carries.** That events carry `session_id` and `cwd` is
  assumed: nothing in the repo shows a real event. Also unverified:
  - that a subagent's tool calls carry its parent's `session_id`;
  - that Stop fires for main sessions only (subagents fire `SubagentStop`, which
    is not wired);
  - that `systemMessage` is honoured on Stop.
- **The append loss.** I measured it with Python's `open(path, "a")` on this
  machine, under artificial contention (8 × 400 appends). The real collision rate
  between two parallel hooks is unmeasured. It is not zero.
- **Finding 1's fix.** The rule is untested. Only the problem was reproduced, in
  this worktree.
