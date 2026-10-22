---
ticket: 216
stage: design
cycle: 2
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "every hook event takes its session root from the event's cwd field when that names an existing directory, and falls back to the process cwd when the field is absent or names no directory, with a test for pre-tool-use, a test for stop, and a test for a cwd that does not exist"
---

# Spec review, cycle 2: the hook runs the main checkout's gate code

**Verdict: `pass`.** I checked only the seven findings from `spec-review.md`,
against `spec.md` at `168025a`. All seven are resolved. Two wording issues
remain, listed at the end. Neither changes a criterion, and both can be fixed
in the plan or the PR body.

## 1. The red test can pass without the real hook answering: resolved

Criterion 1 now reads "the session-start hook prints the real heartbeat
'factory gates: LIVE' and never the shadow's sentinel". The red-test text
asserts both. It also says why the heartbeat matters: it "separates 'the real
factory answered' from 'nothing answered'".

When no venv interpreter is found, the test skips rather than passes. That
covers the vacuous-pass case. In cycle 1 I saw this exact heartbeat come back
from a plain temporary directory under `-I`, so the green side is reachable.

## 2. Blocking stdin read, and untested events: resolved

- **A new criterion:** "when stdin is a terminal the hook reads nothing from
  it". It is tested by injecting `isatty`. I checked pytest's captured-stdin
  stand-in (`_pytest/capture.py`, `DontReadFromInput`): `isatty()` returns a
  bool there rather than raising. So the guard does not break the existing
  in-process tests.
- **Criterion 3** now requires a test for `pre-tool-use`, a test for `stop` and
  a test for a `cwd` that does not exist.

The `stop` test is red today. From an unrelated, non-repository process cwd,
`ticket_worktrees` returns `()` (`git_dir` is `None`), so `_stop_everywhere` is
indifferent whatever the event says. With the change it reaches the ticket
worktree. The plan should name its setup, as it does for the `pre-tool-use`
test.

## 3. The README swap was unexplained: resolved

*Recorded against the issue* explains why the documentation moves to
`factory/AGENTS.md`. The last criterion requires the false console-script
sentence to be corrected.

## 4. The issue's Could-not-verify was dropped: resolved

*Could not verify* now carries two items:

- that the primary checkout is up to date, as the issue requires;
- that bash-run hook tests in a worktree exercise the primary's `factory/`,
  while in-process tests exercise the branch.

## 5. Event `cwd` versus process cwd: resolved

The question is listed under *Could not verify*. See note b on its wording.

## 6. Criterion 5 untested: resolved

The criterion now requires "a copy of the script from a directory with no
venv". The verification section adds no `.git`, so `main_repo` cannot find the
primary's venv either. That is right: without it, a copy placed inside a linked
worktree would still find a venv.

## 7. The red reason was a decode error: resolved

The `cwd` test asserts the output is non-empty before parsing it.

## Notes, not findings

**a. "As the other bash-run tests do" is not quite true.** The bash-run tests
in `test_hook_wiring.py` skip only when `bash` is missing (`needs_bash`). None
skips for a missing venv. The red test therefore needs its own skip condition,
written to match how `factory-hook.sh` searches: the session's `.venv`, then the
primary's. It must not quietly pass when the hook prints `unreachable`. The plan
should say this.

**b. "The change is correct either way, because both fall back to the same
place" overclaims.** If the harness's `cwd` and the process cwd ever differ, the
session root **does** move to the event's `cwd`. That move is the point of
criterion 3, and the intent permits it ("which directory it treats as the
session"). But "correct either way" asserts the very harness behaviour that
this bullet admits it cannot check.

The PR body should say it plainly instead: when they differ, the event's `cwd`
wins, and whether that ever happens in a real session is unverified.

## What this review could not verify

- How Claude Code populates `cwd` for `SessionStart` and `Stop`, and whether it
  follows a Bash `cd`.
- I did not run pytest, and I did not re-run the cycle-1 probes, because the
  spec's mechanism is unchanged.
