---
ticket: 207
stage: review
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: eb232201786249323838fa4395e60bfaf13baec6
---

# Review: Stop judges the session's own worktree and what it wrote, since its base

**Verdict: `changes-requested`.** The code meets all 12 criteria and the red proof
reproduces exactly. Two documentation gaps keep this from passing:

- `docs/factory/README.md` still says Stop runs "across every ticket worktree",
  in its list of what is **[mechanical]**. That is now false.
- `stages.md` leaves out two residuals the build itself found.

Both fixes are small, and one needs the radius widened by one file. There are
also three low-severity code findings. Each has a fix, and none of them blocks.

## Criteria

| # | Criterion (short) | Met | Evidence |
| --- | --- | --- | --- |
| 1 | Base = parent of the first `.factory/<n>/` commit, else the merge-base; red tests for stacked, `dev` moved, pushed, child | Met | `_base` (cli.py). Tests: `test_a_stacked_branch_…`, `test_the_default_branch_moving_…`, `test_a_pushed_branch_…`, `test_a_child_branch_…`, all red without the change. Review 3's "later of" rule is adopted and pinned by `test_the_default_branch_merged_in_…` and `test_a_chain_that_already_sits_…`. My probes are below. |
| 2 | Change set = `diff <base>...HEAD` ∪ `status`, minus `.factory/`; no branch name in added or changed functions | Met | `_changed_paths`. I grepped the added lines in `factory/` for `issue/`, `"dev"` and `movements`: none. The inspect test covers `_base`, `_changed_paths` and `_source_changed`. |
| 3 | Committed source with no plan, then Stop: refused | Met | `test_committed_source_with_no_plan_is_refused`. Red without the change (`assert not True`). |
| 4 | No base: uncommitted paths only, plus the session-start line naming the fix | Met | `test_with_no_base_only_…` and `test_session_start_says_…`. `NO_BASE` names `git remote set-head origin --auto`. |
| 5 | Every refusal names the worktree, the ticket and the base | Met | The `Judged:` line in `_stop_everywhere`. Tested by `test_the_refusal_names_…` and `test_a_refusal_with_no_base_says_so`. |
| 6 | Own ∪ logged; A writing B is judged on both | Met | `test_a_session_that_wrote_another_worktree_…` and `test_the_primary_checkout_on_a_ticket_branch_…`. |
| 7 | Off-ticket session that wrote nowhere: clean; unrelated B mid-build: quiet | Met | `test_a_session_on_no_ticket_…` and `test_an_unrelated_worktree_mid_build_…`. Both red against the old code. |
| 8 | Allowed write outside `.factory/`, into a ticket worktree in the same repository, is logged as one file per worktree | Met | `log_write`; `test_an_allowed_write_records_…`, `test_a_write_into_the_factory_directory_…`, `test_a_refused_write_…`. My multiprocess probe lost no entry (below). |
| 9 | Invalid or missing `session_id` writes no log | Met | `SESSION_ID` regex, plus 9 parametrised cases including `None`, `7`, `"../x"` and 129 characters. |
| 10 | The log can never change the answer: forced raise, deny still prints | Met | `test_the_write_log_can_never_change_the_answer` patches both log functions to raise. The deny still prints, the allowed write is still `{}`, and Stop still blocks on the session's own worktree. |
| 11 | Changed tests named; `decide_stop` signature unchanged; suite green | Met | Exactly the seven named tests changed. `hooks.py` is untouched. Full suite: `1 failed, 1278 passed, 3 skipped, 25 deselected`. The one failure is the flaky #229 test, which passed 3 of 3 runs on its own. |
| 12 | `stages.md`: what Stop sees, shell writes `[unenforced]`, `set-head` | Met, with gaps | All three are present. Finding 2 lists what is missing. |

## Checks I ran

- **Red proof.** I reverted `factory/cli.py`, `factory/worktrees.py`,
  `factory/AGENTS.md`, `stages.md` and `design.md` to `6a98977`, kept every test,
  and ran `test_stop_scope.py` and `test_cli.py`.
  - **`test_stop_scope.py`: exactly 26 failures**, for the stated reasons:
    - 9 × `no attribute '_base'`;
    - 2 × `_changed_paths`;
    - `log_write` absent: the `sessions/s1` path is missing, `is_dir()` is False, and the forced-raise test's `monkeypatch` fails;
    - `assert not True` for committed source;
    - `'<wt>' in ''` and the missing `Judged:` text;
    - 2 × `KeyError: 'decision'`;
    - `'not checked' in <report>`;
    - 2 × "unrelated worktree blocks": `{'decision': 'block', …} == {}`.
  - **`test_cli.py`: 3 of the 7 changed tests fail**, with a `TypeError` on the
    new `session_id` argument. The other 4 pass on the old code. That is expected:
    they pin #216's `cwd` resolution, and the old code judged every worktree, which
    includes the logged one. The scope behaviour itself is pinned by
    `test_stop_scope.py`.
  - I restored everything afterwards. `git status` is clean and
    `tests/test_factory` gives 350 passed.
- **`_base` on real scratch repositories** (`probe207/base_probe.py` in my
  scratchpad).

  | Case | Result |
  | --- | --- |
  | Rebase onto a moved `dev` | base = new `dev` tip, `{src.py}` |
  | Squash of chain + source into one commit | base = `dev`, both source files counted |
  | Two chain commits | the oldest commit wins, `{src.py, src2.py}` |
  | No `.factory` commit | merge-base, `{src.py}` |
  | `origin/HEAD` deleted, chain present | `f^`, `{src.py}` |
  | `origin/HEAD` deleted, no chain | no base, `set()` (committed source unseen, as specified) |
  | Merge `dev` in, more work, `dev` moves again | base = the merged-in tip, `{own.py, own2.py}` |
  | Stacked; parent merged with a merge commit; child merges `dev` | base = `dev` tip, `{two.py}` |
  | Chain already on `dev` (reopened ticket) | base = `dev` tip, `{src.py}` |
  | **Stacked; parent squash-merged; child merges `dev`** | **neither base is an ancestor of the other, so `f^` is taken: `{two.py, dev.py}`**. An over-refusal; see finding 2. |

  No case lets committed source escape apart from the specified no-base case.
- **Concurrency** (`probe207/conc_probe.py`). 48 separate `python -m factory hook
  pre-tool-use` processes ran at once, 6 per worktree across 8 worktrees, all with
  one `session_id`.
  - Every process exited 0 with no output.
  - The log held exactly 8 entries, all non-empty, matching the 8 resolved roots.
  - Stop over those 8 logged worktrees, 2 of them with committed source, blocked in 1.1 s.
- **PreToolUse cost.** By inspection, `log_write` uses `governing`, `common_dir`,
  `hashlib` and one `mkdir` plus `write_text`, and starts no process.
  `test_pre_tool_use_runs_no_subprocess` patches `subprocess.run` and `Popen` to
  raise. The log is written only in the `decision.allowed` branch, inside
  `contextlib.suppress(Exception)`.
- **Ruff, pyright and the suite.**
  - `ruff check` and `ruff format --check` on `factory` and `tests/test_factory`: clean.
  - `pyright` on the four changed Python files: 0 errors.
  - Full suite: as in criterion 11.

## Findings

### 1. `docs/factory/README.md` overstates what Stop enforces (changes requested)

Line 30, in the list of what is **[mechanical]** today, says: "the proof before a
turn ends, **across every ticket worktree** (`Stop`, #206)". After this change
Stop judges the session's own worktree plus the ones it wrote, and nothing else.
That list exists "so the list can be checked rather than believed". It is the same
kind of false-in-the-docs problem as d5.

**Fix.** Add `docs/factory/README.md` to the radius and reword the line, for
example: "the proof before a turn ends, for the session's own ticket worktree and
every worktree it wrote (`Stop`, #206, #207)".

### 2. `stages.md` omits two residuals the build itself found (changes requested)

- **A session that leaves the repository loses its write log** (plan,
  deviation 2). This contradicts a spec decision, which said the log survives.
  - **Acceptable on the merits.** It is no regression, since before #207
    `ticket_worktrees(<outside>)` judged nothing either. It also needs the session's
    `cwd` to leave the repository entirely.
  - **But it is recorded only in the plan.** `stages.md` says Stop judges "every
    ticket worktree the session wrote with an edit tool", with no qualification.
    The plan and PR body are not where a later reader looks for the gate's limits.
- **A stacked ticket whose parent was squash-merged, then merged `dev` in, is
  over-refused** for the parent's squashed commit and anything else on `dev`. My
  probe shows this above. It is not an escape, and this repository merges with
  merge commits today, but the "later of" rule's precondition (that one base is
  an ancestor of the other) silently stops holding.

**Fix.** Add both to the `stages.md` bullets beside the existing `[unenforced]`
items. For example: "a session whose `cwd` leaves the repository before Stop is
judged on nothing, its log included", and "after a squash-merged parent, merging
the default branch in over-refuses; rebase instead".

### 3. `common_dir` duplicates `hooks._common`, including its known trap (low)

`worktrees.common_dir` is a line-for-line copy of `hooks._common`. Both test
`found.parent.name == "worktrees"`, which `hooks._is_primary`'s own docstring
names as wrong for a repository whose directory is called `worktrees`.

**Probed.** In a primary checkout at `<tmp>/worktrees`:

- `common_dir` returns `<tmp>`, but the linked worktree's common dir is `<tmp>/worktrees/.git`;
- so a session in that primary writing worktree B logs nothing;
- so its Stop does not judge B.

The defect is inherited and the case is rare, but the new copy doubles it.

**Fix**, now or as a follow-up: read `<gitdir>/commondir`, which git writes in
every linked worktree's git dir, in one shared helper, and use it from both modules.

### 4. An empty log entry reads as `Path(".")` (low)

`logged_worktrees` does `Path(entry.read_text().strip())`. For an empty file that
is `Path(".")`, which `is_dir()`. It then judges the hook process's cwd as a
logged worktree.

**Probed:** `logged_worktrees(b, "s2")` with one empty entry returned
`(WindowsPath('.'),)`.

**How it is reached:** only through a truncated write, or a reader racing
`write_text`'s truncate.

**Fix:** `if not text: continue`. Optionally, skip `write_text` when the entry
already exists, which also stops every allowed edit from rewriting the file.

### 5. Small accuracy notes (low, no change needed to pass)

- **Stop's cost is about six git processes per judged worktree, not five:**
  `log`, `rev-parse`, `merge-base`, `merge-base --is-ancestor`, `diff`, `status`.
  The first refusal runs `_base` again, which adds four more. It is bounded by
  1 + the number of distinct worktrees in the session's log, but the `git log`
  walk is O(history).
  - Each call has a 10 s timeout, inside the 15 s Stop budget in
    `.claude/settings.json`. A harness timeout lets the turn end.
  - Nothing is unbounded. Computing the base once per worktree and passing it to
    the refusal would save the duplicate run.
- **`design.md` d3 still cites `cli.py:438`.** `_stop_everywhere` is now at line 583.
- **The plan's changed-tests intro says each entry is "written through
  `log_write`".** The Proof section correctly says `_logged` writes it by hand.
- **`ticket_worktrees` is now dead in production.** It is kept in `cli.py` only
  as a re-export (`# noqa: PLC0414`) for `test_cli.py`'s import and
  `test_ticket_worktrees_is_the_same_function_the_cli_exports`. This is disclosed,
  and acceptable.

## The `_logged` helper: it does not hide a defect

The `test_cli.py` fixtures give each fake linked worktree its own `.git`
**directory**. `common_dir` therefore reads each one as its own repository, and
`log_write` would rightly refuse it. Writing the log by hand tests what Stop reads
from the log, which is the behaviour those seven tests pin (scope and #216's
`cwd` handling).

The path a real worktree takes is covered on real repositories that share one
common dir:

- `log_write` on real linked worktrees, from a linked worktree and from the
  primary checkout (`test_a_session_that_wrote_another_…`,
  `test_the_primary_checkout_on_a_ticket_branch_…`,
  `test_an_allowed_write_records_…`, `test_concurrent_writers_…`);
- my 48-process probe.

The helper names its files by `root.name` rather than by SHA-1. The reader does
not depend on the name, so that is harmless. The rewrites are honest: each test
keeps its original assertion and gains only a `session_id` and a log entry.

## Could not verify

- **The harness.** That events carry `session_id` and `cwd`, and whether a
  subagent's tool calls share the parent's `session_id`. If they share it, an
  orchestrator's Stop is held to what its subagents wrote. No live Claude Code
  session was run.
- **A fetched `origin/HEAD`.** Like the tests, my probes used `update-ref` and
  `symbolic-ref`.
- **A real shallow clone.** A root commit stood in for it.
- **Paths that git quotes** (a `"` or a control character) in `diff --name-only`
  output. Windows forbids those names, so I could not create them here. A quoted
  `.factory/` path would escape the prefix filter and over-refuse.
- **Windows case and 8.3 spellings** of one worktree in the log.
- **Hook latency on a cold disk or a larger history.** Measured only here: 1.1 s
  for 8 logged worktrees.
