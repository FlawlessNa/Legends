---
ticket: 207
stage: review
cycle: 2
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: c12a5a3837c14857a9d9919542f5390be5f5aa5e
---

# Review, cycle 2: the five findings of `review.md`

**Verdict: `changes-requested`, on one line of code.** Findings 1, 2, 4 and 5 are
fixed. Finding 3 fixed the `worktrees`-named primary, but its fallback opened two
new mis-identifications. `common_dir` now reports a submodule as **the same
repository as its superproject**. It reports a `--separate-git-dir` checkout as
an unrelated directory. Before this cycle, both cases got their own git directory
back.

The fix is one line plus a test. Nothing else is open.

## The five findings

| # | Finding | Status | Evidence |
| --- | --- | --- | --- |
| 1 | README overstated Stop's scope | Fixed | `docs/factory/README.md:30` now reads "over the session's own worktree and the ticket worktrees it wrote (`Stop`, #206, #207)". The file is in the radius. |
| 2 | `stages.md` omitted two limits | Fixed | The "Two limits" bullet records both limits. A session that leaves the repository loses its log, which is "no worse than before #207". A squash-merged parent followed by merging `dev` in over-refuses, and rebasing avoids it. |
| 3 | `common_dir` duplicated, and fell into the `worktrees` name trap | **Fixed, but with a new regression** | One `chain.common_dir`. `hooks._common` delegates to it, and the copy in `worktrees.py` is gone. The `worktrees`-named primary is fixed. The fallback is not: see the finding below. |
| 4 | An empty log entry read as `Path(".")` | Fixed | `logged_worktrees` skips empty and whitespace-only text. |
| 5 | Accuracy notes | Fixed | d3 no longer cites a line number. The plan now says the entries are written "by hand (`_logged`)". The cost is now "about six … plus four more on a refusal". |

### Red tests for the fixes

I reverted `factory/chain.py`, `factory/hooks.py` and `factory/worktrees.py` to
`eb23220`, kept every test, and ran the new tests:

- **`test_a_primary_checkout_in_a_folder_named_worktrees_is_its_own_repository`:
  red, for the right reason.** `_common(<tmp>/worktrees)` returned `<tmp>`.
- **`test_an_empty_log_entry_is_skipped_…` with `""`, `"  "` and `"\n"`: all
  three red.** Each returned `(WindowsPath('.'),) == ()`.
- **`test_a_linked_worktree_and_its_primary_share_one_repository`: green before
  and after.** It is a guard, as the builder said.
- **Restored afterwards.** `git status` is clean.

### #206 and #209 behaviour

`test_hooks.py` is unchanged, and all 76 of its tests pass. On standard layouts the
identity is the same as before, as the probe below confirms: a primary checkout,
and a linked worktree whose `commondir` file reads `../..`.

The hand-built fixtures have no `commondir` file, so they take the
`found.parent.parent` fallback. They get the same answer as before.

## Finding: the fallback for a missing `commondir` is now unconditional (changes requested)

`common_dir` decides a primary checkout by `.git` being a directory, which is
right. Next it reads `commondir`. Without that file, it returns
`found.parent.parent` **whatever the layout**.

The docstring says that path is for "a hand-built fixture". Real repositories take
it too: git writes no `commondir` file for a submodule or a `--separate-git-dir`
checkout. Their `.git` is a file whose git directory is itself the common dir.

**Probed.** My scratchpad script `probe207/common_probe.py` compares each answer
with `git rev-parse --git-common-dir`:

| Layout | Cycle 1 (`hooks._common`) | Cycle 2 (`chain.common_dir`) | git |
| --- | --- | --- | --- |
| Primary in a folder named `worktrees` | `<tmp>` (wrong) | `<tmp>/worktrees/.git` | `<tmp>/worktrees/.git` |
| Linked worktree | `<primary>/.git` | `<primary>/.git` | `<primary>/.git` |
| Submodule `mod` | `.git/modules/mod` | **`<superproject>/.git`** | `.git/modules/mod` |
| `--separate-git-dir=<tmp>/sepgit` | `<tmp>/sepgit` | **`%TEMP%`**, two levels up | `<tmp>/sepgit` |

**Why the submodule case matters.** Identity is the check behind #206's row 3
(`decide_write`) and #209's row 1. A submodule that reads as its superproject is
the exact confusion `_common`'s docstring exists to prevent.

This is also how it reaches the gates: a session on a ticket can now have a
write into a submodule judged against its own chain, where before it was
indifferent. `ticket_worktrees(<submodule>)` would also list the superproject's
worktrees.

Legends has no `.gitmodules` and does not use a separate git directory, so none
of this is reachable today. It is still a regression in a protected identity
helper, introduced by this cycle, and the docstring's claim about who takes the
fallback is false.

**Fix.** Keep the layout rule only for the case it describes:

```python
return found.parent.parent if found.parent.name == "worktrees" else found
```

The primary checkout is already decided by shape on the line above, so the name
trap from finding 3 cannot come back. Reword the docstring to say which layouts
take the fallback.

**Red test.** A real `git submodule add`, or `git init --separate-git-dir`, in
`tmp_path`, where `common_dir` must equal `git rev-parse --git-common-dir`. It
goes red on `c12a5a3`.

## Gates

| Gate | Result |
| --- | --- |
| `ruff check`, `ruff format --check` (`factory`, `tests/test_factory`) | clean |
| `pyright --pythonpath <venv python>` on `factory` and `tests/test_factory` | 0 errors |
| Full suite from the worktree root | `1284 passed, 3 skipped, 25 deselected`. Nothing failed, and #229 did not fire. |

## Could not verify

- **The cycle-2 tests were not added to `red207.txt`.** I re-ran them red myself
  (above), so the proof holds, but the plan's `red_output_sha` covers only the
  original 26.
- **The previous cycle's harness and environment gaps stand as written in
  `review.md`.** These are: `session_id` behaviour, a fetched `origin/HEAD`, a
  shallow clone, quoted paths, Windows path spellings, and latency.
