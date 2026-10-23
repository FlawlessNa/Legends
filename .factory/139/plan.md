---
ticket: 139
stage: build
radius:
  - factory/chain.py
  - tests/test_factory/test_chain.py
  - docs/factory/artifacts.md
  - .factory/139/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_chain.py
  red_output_sha: 4c916731681b
  suite: pass
docs_cleared: []
---

# Plan: chain v2

## Radius

| Path | Why |
| --- | --- |
| `factory/chain.py` | `front_matter_lists`, the new `Chain` fields, `LOOP_ARTIFACTS`, `version` and `UnknownChainVersion`, `blob`, `radius_errors` |
| `tests/test_factory/test_chain.py` | New. Every criterion's tests, and the real-chain test |
| `docs/factory/artifacts.md` | The new contracts, the radius grammar, and the list grammar. Removes the Supersedes bullet for #139, which this lands. |

**Not in the radius:** `routing.py`, `hooks.py` and `cli.py`. No caller changes. If one has to, this plan is wrong.

## Two rules the spec left to the plan (spec-review-2)

- **Where a block list ends.** A list's items are the indented lines beginning `- ` after `key:`, up to the next non-blank line at column 0. Blank lines and lines whose stripped text starts with `#` are skipped inside a list. Any other indented line inside it makes the key absent, because it is a nested structure, not a list of scalars.
- **`blob` with no `git` on PATH returns `None`.** That matches the module's rule that missing means absent, never an error. The test repo sets `user.name`, `user.email` and an empty `core.hooksPath` before committing.

## Order of work

1. Write `test_chain.py`. Run it against the unchanged `chain.py` and record the failures (import errors, since none of the names exist).
2. Implement. Run green.
3. Write the `artifacts.md` contracts.
4. Run the full suite, unmodified.

## Proof

**Red, before the change**: `tests/test_factory/test_chain.py` against the unchanged `chain.py`:

```
ImportError while importing test module 'C:\Users\Nassim\.herdr\worktrees\Legends\issue-139-chain-v2\tests\test_factory\test_chain.py'.
E   ImportError: cannot import name 'LOOP_ARTIFACTS' from 'factory.chain' (C:\Users\Nassim\.herdr\worktrees\Legends\issue-139-chain-v2\factory\chain.py)
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.51s
```

The failure is an import error at collection, because none of the names the criteria require existed: `LOOP_ARTIFACTS`, `UnknownChainVersion`, `blob`, `front_matter_lists` and `radius_errors`.

**Green, after**: `pytest` from the worktree root gave `1260 passed, 3 skipped, 25 deselected`, with 0 failed, 0 errors and 0 xfailed. The existing suite is unmodified. `ruff check` and `ruff format` are clean. pyright reports only `pytest` unresolved, because the worktree has no `.venv`; pre-commit passed on commit.

## Deviation from the spec, recorded

The spec's Shape gives `blob` as `rev-parse --verify --quiet <commit>:<path>^{blob}`. **That command fails for every file.** Git reads `^{blob}` as part of the path: in this repo, `git rev-parse --verify --quiet "HEAD:factory/chain.py^{blob}"` exits 1, while the same path without the peel exits 0. So `blob` uses `git ls-tree <commit> -- <path>`, and accepts the entry only when its type is `blob` and its path matches exactly. The criterion is unchanged: the blob id, `None` for a missing commit, path or directory, and the LF id under CRLF. All of it is tested.

## Could not verify

- The cost of reading five more files, and the lists, in `read_chain`. The hooks call it on every edit. They are small stat-and-read calls, but they were not timed.
- Whether a future chain writes a list form this grammar refuses. It is refused visibly (the key is absent), never half-read.
