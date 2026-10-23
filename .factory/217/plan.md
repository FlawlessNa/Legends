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
  red_output_sha: cb06bbefcdcc
  suite: pass
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

## Proof

**Red, before the change.** The new tests were run against the unchanged source. `PullRequestFacts` was given an inert `default_branch: str = ''` field *only* so `test_merge.py` could be collected at all (otherwise the whole module is one `TypeError`); that stub was reverted before the implementation. The `E` lines are in the scratchpad file `red217.txt` (sha256 prefix `cb06bbefcdcc`). 26 failed, 1 collection error (`test_worktrees.py`: `ModuleNotFoundError: No module named 'factory.worktrees'`). The reasons:

```
E   AssertionError: assert ['.github/**'.../cli.py', ...] == ['.github/**'...est_merge.py']
E     At index 2 diff: 'factory/__init__.py' != 'factory/**'                  (protected set is one path)
E   AssertionError: assert NOT_SELF_CHANGE in {WORKING_BRANCH}                (unimported factory module unprotected)
E   AssertionError: ... reason='Base is dev; only movements-improvements is merged by CI.'   (working branch not the default branch)
E   AssertionError: assert not True  where True = hasattr(Policy(working_branch=...))
E   KeyError: 'default_branch'                                                (gather does not read it)
E   assert <ExitCode.OK: 0> == <ExitCode.NEEDS_HUMAN: 3>                      (empty default branch / failing repo call not refused)
E   AssertionError: assert 'plan' == 'design'                                 (chain read from the session, not the ticket's worktree)
E   AssertionError: assert 0 == <ExitCode.MISUSE: 2>                          (no worktree for the ticket)
E   AssertionError: assert 0 == <ExitCode.NEEDS_HUMAN: 3>                     (two worktrees for one ticket)
E   AssertionError: assert 'sonnet' == 'opus'                                 (table read from the ticket's checkout)
E   Extra items in the left set: '.claude/**' / Extra items in the right set: '.factory/**'   (condition 4 row vs allowed_paths)
```

The protected-set document test cannot be red against the old `POLICY`; it is red only as new POLICY, old document, and was run in that state (second block of `red217.txt`): the document listed the nine modules, `POLICY` held `factory/**`. Two cli tests (primary on the ticket branch, run from its root) passed before the change, because they guard against the double-count regression the change could introduce.

**Green, after.** `pytest` from the worktree root: `1240 passed, 3 skipped, 25 deselected`, 0 failed, 0 errors, 0 xfailed. `ruff check`, `ruff format` and `pyright` are clean on the changed Python files, and pre-commit passed on commit `2e52753`.

## Could not verify

- **That the workflow is on `dev` and merges nothing.** The page now says so on the spec's word; nothing here read GitHub's state.
- **`gh api repos/<repo> --jq .default_branch` against the live API.** `FakeGh` answers it with the raw text the spec says was recorded; the real call was not run by this builder.
- **Real-worktree behaviour.** `worktree_for` is tested on fabricated `.git` layouts, not on `git worktree add` output. Windows case-insensitivity is covered by one test only on win32.
- **`model --stage S <n>` with no worktree now exits 2** (previously it read the current directory). Callers that relied on that will see MISUSE.
- **This PR fails working-branch with exit 3 until retargeted**: the workflow runs #226's `merge.py`, which still names `movements-improvements`. Retarget to `dev` after #226 merges; "Closes #217" fires only once it reaches `dev`.
- A session in a subdirectory of a plain (non-ticket) checkout now has `factory next` (no ticket) read the worktree root rather than the subdirectory; no test pins the old behaviour.
