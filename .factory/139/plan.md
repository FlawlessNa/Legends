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
  red_output_sha: see Proof below
  suite: null
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
