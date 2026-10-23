---
ticket: 207
stage: review
cycle: 3
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-23
commit: 562892f4db3e1e797b615975125a20df84357373
---

# Review, cycle 3: the `common_dir` regression

**Verdict: `pass`.** I checked only the regression found in `review-2.md`. It is
fixed, and each of its two new tests goes red without the fix.

## The fix

When a linked worktree's git directory has no `commondir` file, `chain.common_dir`
now returns `found.parent.parent` only if `found.parent.name == "worktrees"`.
Otherwise it returns `found`, the git directory itself.

The primary-checkout check still comes first, on the shape of `.git`, so the
`worktrees`-named primary from cycle 1 stays fixed. The docstring now names
submodules and `--separate-git-dir` as layouts with no `commondir` file, which is
accurate.

## Red tests

I reverted only `factory/chain.py` to `c12a5a3`, kept the tests, ran the two new
tests, and then restored the file. `git status` was clean afterwards.

| Test | On `c12a5a3`'s `chain.py` | On `562892f` |
| --- | --- | --- |
| `test_a_separate_git_dir_checkout_is_its_own_repository` | red: `<tmp>` returned, where git gives `<tmp>/elsewhere/g.git` | green |
| `test_a_submodule_is_its_own_repository_not_its_superproject` | red: `sup/.git` returned, where git gives `sup/.git/modules/sub` | green |

Both compare against `git rev-parse --path-format=absolute --git-common-dir` on
real repositories, and the submodule is a real `git submodule add`. The second
test also asserts that the submodule's answer differs from the superproject's.

## Probe

I re-ran `probe207/common_probe.py` from my scratchpad against `562892f`'s
`factory/`. It agrees with git on all four layouts:

| Layout | `common_dir` | git |
| --- | --- | --- |
| `--separate-git-dir` | `<tmp>/sepgit` | `<tmp>/sepgit` |
| Primary checkout in a folder named `worktrees` | `<tmp>/worktrees/.git` | the same |
| Linked worktree | `<primary>/.git` | the same |
| Submodule `mod` | `<primary>/.git/modules/mod` | the same |

## Gates

| Gate | Result |
| --- | --- |
| `ruff check`, `ruff format --check` (`factory`, `tests/test_factory`) | clean |
| `pyright --pythonpath <venv python>` (`factory`, `tests/test_factory`) | 0 errors |
| `tests/test_factory/test_hooks.py` (#206, #209) | 76 passed, unchanged |
| `tests/test_factory`, three runs in a row | 357 passed each time |
| Full suite | `1286 passed, 3 skipped, 25 deselected`, on two of three runs. |

The first full-suite run had one failure, which I did not capture: I ran it
without `-rf`. It did not come back:

- two further full runs passed;
- three runs of `tests/test_factory` passed;
- a separate run of `test_hooks.py` passed.

It was most likely the known flaky #229 test, but I cannot confirm that.

## Could not verify

- **The test behind the single unidentified failure** in the first full-suite run.
  `tests/test_factory` passed three times running, so I have no evidence that it
  came from this change.
- **`red207.txt` was not regenerated for the four tests added in review.** I ran
  each of them red myself, in cycle 2 and in this cycle.
- **The harness and environment gaps listed in `review.md` remain open.** They are
  listed there and were not re-examined in this cycle.
