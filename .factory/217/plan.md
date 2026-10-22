---
ticket: 217
stage: build
radius:
  - factory/merge.py
  - factory/worktrees.py
  - factory/cli.py
  - factory/AGENTS.md
  - tests/test_factory/test_merge.py
  - tests/test_factory/test_cli.py
  - tests/test_factory/test_worktrees.py
  - docs/factory/merge-policy.md
  - docs/factory/design.md
  - .gitattributes
  - .factory/217/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_merge.py::test_the_protected_set_names_the_factory_package_as_one_path
  red_output_sha: see Proof below
  suite: null
docs_cleared: []
---

# Plan: protect factory/** as one path, resolve a ticket's own worktree, read the default branch

## Radius

| Path | Why |
| --- | --- |
| `factory/merge.py` | `factory/**` replaces nine entries; `working_branch` removed; `default_branch` in the facts, gathered and compared; payload gains it |
| `factory/worktrees.py` | new: `ticket_worktrees` moved verbatim, and `worktree_for` |
| `factory/cli.py` | imports both names; `_next` and `_model` take the chain from the ticket's own worktree |
| `factory/AGENTS.md` | the "add each module by hand" paragraph, and the new module |
| `tests/test_factory/test_merge.py` | red tests and the named changed tests below |
| `tests/test_factory/test_cli.py` | red tests for `next`/`model` and the named changed tests below |
| `tests/test_factory/test_worktrees.py` | new: `worktree_for`, including the dedup case |
| `docs/factory/merge-policy.md` | made true: condition 4 and 8, protected set, what is live |
| `docs/factory/design.md` | R11, §10 name `dev`; d6 records the fix |
| `.gitattributes` | `.factory/** text eol=lf` |

`factory/hooks.py` is **not** in the radius: `governing` is used as it is.
`factory/**` is a protected path, so this PR is a human merge regardless.

## Order of work

1. Write the red tests; run them against the unchanged source; save the failures.
2. `merge.py`, then `worktrees.py` and `cli.py`; tests green.
3. The four docs and `.gitattributes`.
4. Full suite, ruff, pyright.

## Two notes from the passing spec review, taken here

- **`worktree_for` deduplicates by `Path` equality, not by string.** `resolve()` changes case on Windows, so strings differ for the same directory. Without it the primary checkout, when it is the session and is on the ticket branch, is found twice (once as the session root in `ticket_worktrees`, once as the primary) and trips the exit-3 ambiguity. Tests: the session is the primary on the ticket branch, run from its root and from a subdirectory; each must give exactly one worktree.
- **The protected-set document test is red only as "new POLICY, old document".** Today the document lists nine module entries; the test fails because `factory/**` is in POLICY and not in the document, not because the document is wrong in itself. It parses only path-like backticked tokens (containing `/` or a leading dot), so the bare `` `factory` `` is not read as a path.

## Changed tests

| Test | Behaviour that moved |
| --- | --- |
| `_passing` (test_merge.py) | `base="trunk"`, `default_branch="trunk"`; not `dev`, so the `base="dev"` failure cases keep their meaning |
| `FakeGh` (test_merge.py) | answers the repository call with raw `movements-improvements\n`, matching `_VIEW` |
| `test_the_document_states_every_condition_and_value` | drops `POLICY.working_branch`, which no longer exists |
| `test_the_ticket_form_computes_the_stage_from_the_chain` (test_cli.py) | the ticket form now needs the ticket's worktree, so the test builds one |
| `test_a_blocked_chain_needs_a_human_and_says_why` (test_cli.py) | same |
| `test_every_module_the_console_script_imports_is_protected` | unchanged in text; it passes through `factory/**` |

Any other test changed is added here with its reason.

## For the PR body

- `factory model --stage S <n>` with no worktree for `n` now exits 2: the ticket form always needs the ticket's worktree, because overrides read its chain.
- The branch is stacked on #216; the workflow still runs #226's `merge.py`, which names `movements-improvements`, so this PR fails working-branch with exit 3. Retarget to `dev` after #226 merges.
