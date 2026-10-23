---
ticket: 139
stage: review
cycle: 2
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 8b6e44a7b9d3c5639ff49282b4d1859658da4c3c
---

# Review, cycle 2: chain v2

**Verdict: `pass`.** I checked only the six findings in `review.md`, against
`8b6e44a` (diff `6a87bc0..8b6e44a`). All six are resolved. Two small notes are
left, and neither blocks.

## Findings

| # | Finding | Result | Evidence |
| --- | --- | --- | --- |
| F1 | Column-0 comment truncates a list; column-0 items read as `()` | Resolved | Whole-line `#` is skipped before the column-0 branch. A column-0 `-` line while a key is open sets `broken`. My cycle-1 probes now give `col0_comment_inside` → `('a.py', 'b.py')` and `col0_items` → absent. |
| F2 | `blob` misses C-quoted paths, raises under `quotePath=false`, and takes a `-` commit as a flag | Resolved | Details below. |
| F3 | Empty key reads as `()`; duplicate keys disagree with `front_matter` | Resolved | `key:` with no items is now absent (`items` must be non-empty to record). `found.pop(name)` on every column-0 key makes the last occurrence win. My probes: `empty_value_no_items` and `empty_value_last` → `{}`; `list_then_scalar` → `{}`, which matches `front_matter`'s scalar; `scalar_then_list` → `('b.py',)`. `docs_cleared: []` still reads as `()`. |
| F4 | `artifacts.md` omits wrapping and trailing-comment traps | Resolved | Three traps are now listed: wrapping, trailing `# comment`, and null vs `[]`. The absent-list sentence now names nested lists, column-0 items, and tab-vs-space. |
| F5 | `artifacts.md` gaps against design §6 | Resolved | `proof.md` gains `suite_output` and `red_output` (sha256), which is design §6's "output digests". `intent.md` records that `accepted_by`/`accepted_at` are retired in v2. `stages.md:282` is left for #218, which is outside this radius and acceptable. |
| F6 | Test and code notes | Resolved | `commit.gpgsign=false` is in the fixture. `- - a` is now absent and tested. Indentation is compared as the literal leading string, so tab vs space is absent and tested. The loop-artifacts test asserts `answers.md`. |

### F2 in detail

- **Quoted paths now resolve.** `ls-tree -z --end-of-options`, with bytes
  stdout, path decoded as UTF-8 with surrogateescape. The scratch repo from
  cycle 1 now resolves `déjà.md`, `q"uote.md` and `t<TAB>ab.md` (the last two
  are `git mktree` objects) to the same id as `git rev-parse HEAD:<path>`.
- **No more raise.** With `core.quotePath=false`, `café.md` and `”q.md` now
  return their ids. Cycle 1 returned `None` and raised `AttributeError`.
- **Earlier cases unchanged.** Spaces, `#`, `[`, a leading `-`, directories
  with and without `/`, missing paths, globs, pathspec magic, and bad commits
  (`nope`, forty zeros, `HEAD~5`, `-r`) answer as in cycle 1.
- **`--help` no longer opens a browser.**
  - `test_a_commit_that_looks_like_a_flag_is_not_one` passed in 1.40 s.
  - A process scan straight afterwards found no `git web--browse` or
    `git-ls-tree.html` process.
  - `GIT_TRACE=1 git ls-tree -z --end-of-options --help -- dir/x.md` shows the
    built-in run with `fatal: Not a valid object name --help`, exit 128.
  - My probe script also returned `None` for `--help` without hanging.
- **The red tests.** I wrote `factory/chain.py` at `6a87bc0` over the file,
  kept HEAD's tests, and ran `test_chain.py` without the `--help` test, since
  under the old code that test opens a browser. 7 failed, 64 passed, 1
  deselected:
  - the six new list tests;
  - `test_blob_finds_files_git_would_quote[ünïcode.md]`.

  `[with space.md]` passed under the old code too, because git never quoted
  spaces. It is a regression guard, not a red test. Afterwards I restored the
  file with `git checkout HEAD -- factory/chain.py`, and `git status` was clean.

## Notes, not findings

- **A literal backslash in a tracked path still answers `None`.** Git for
  Windows turns `\` in a *pathspec* into `/`. For a commit whose tree holds
  `back\slash.md`:
  - `git rev-parse <c>:back\slash.md` finds it;
  - `git ls-tree -z <c> -- 'back\slash.md'` prints nothing, and so does the
    `:(literal)` form.

  Such a path cannot be checked out on Windows, and `radius_errors` rejects
  backslashes, so no caller can reach it. The docstring's "a backslash" in its
  list of quoted characters is true of `-z` output, not of the lookup. Leave it,
  or drop the word.
- **Two cosmetic points in `artifacts.md`.**
  - The block-list bullet still says "up to the next non-blank line at column
    0". The next sentence, and the function's docstring, say comments are
    skipped at column 0 too. "Non-blank, non-comment" would match the code.
  - The v2 retirement note sits on the `accepted_at` row, not on
    `accepted_by`'s.

## Gates re-run at `8b6e44a`

- **Full suite.**
  `C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider`
  from the worktree root gave `1269 passed, 3 skipped, 25 deselected`, with 0
  failed, 0 errors and 0 xfailed. The skips are the same three pre-existing
  `movement_lab` Expectation skips. The thirteen committed-chain tests still
  pass.
- **Ruff.** `ruff check` gave "All checks passed!" and `ruff format --check`
  gave "2 files already formatted", on `factory/chain.py` and
  `tests/test_factory/test_chain.py`.
- **Pyright.**
  `pyright --pythonpath C:/Users/Nassim/code/Legends/.venv/Scripts/python.exe`
  on the same two files reported 0 errors and 0 warnings.
- **Radius.** The diff `6a87bc0..8b6e44a` touches only `factory/chain.py`,
  `tests/test_factory/test_chain.py`, `docs/factory/artifacts.md` and
  `.factory/139/review.md`, all inside the radius.

## What I could not verify

- **Other git versions or platforms.** `blob` was checked only on Git for
  Windows 2.39.1. On POSIX git the backslash note above likely does not apply.
- **The digest field names.** That `suite_output`/`red_output` are the names
  #145 will want. Design §6 says only "output digests". #145 may rename them.
- **`chain: 2` chains and the real loop.** As in cycle 1, neither exists yet.
