---
ticket: 217
stage: review
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 016692bf8bf0fe0ac502cb29e25dbd1afe10d424
---

# Review: protect factory/** as one path, resolve a ticket's own worktree, make merge-policy.md true, read the default branch

**Verdict: `pass`.** All 14 criteria are met. I reproduced the red proof myself
and its stated reasons hold. I have six notes. None of them changes whether a
criterion is met. Three should be fixed in the PR body before a human merges:
findings 1, 3 and 4.

I reviewed `git diff ac104aa..HEAD -- . ':!.factory'` against `spec.md`,
`spec-review-2.md`'s two notes, and `plan.md`.

## Criteria

| # | Criterion (short) | Met | Evidence |
| --- | --- | --- | --- |
| 1 | `protected_paths` holds one factory entry, `factory/**`, alongside the three others; a test fails if it is removed | met | merge.py `protected_paths` is exactly `docs/factory/merge-policy.md`, `tests/test_factory/test_merge.py`, `.github/**`, `factory/**`. `test_the_protected_set_names_the_factory_package_as_one_path` asserts the sorted list, and was red against the old source: `At index 2 diff: 'factory/__init__.py' != 'factory/**'`. |
| 2 | The console script's import closure is protected, and so is a factory module it does not import | met | `test_every_module_the_console_script_imports_is_protected` is unchanged and passes. `test_a_factory_module_the_console_script_does_not_import_is_protected` was red before the change (`NOT_SELF_CHANGE in {WORKING_BRANCH}`) and is green now. |
| 3 | No `working_branch` field; the grep finds only the three allowed hits | met | `grep -rn movements-improvements factory docs/factory` finds `factory/hooks.py:504` (the comment that the trunk may move), `docs/factory/design.md:14` and `design.md:98` (d6). It also matches `factory/__pycache__/hooks.cpython-314.pyc`, a gitignored binary (`.gitignore:2`) that is not in the tree. `test_the_policy_holds_no_branch_name` covers the removed field. |
| 4 | `PullRequestFacts.default_branch`; `gather` reads it with `gh api repos/<repo> --jq .default_branch`, strips it, raises `FactsUnreadable` when it is empty or the call fails, each with a test | met | merge.py `gather` makes that call, strips the output, and raises on empty output. The real `run_gh` raises `FactsUnreadable` on a non-zero exit (merge.py:457–458). Three tests cover this: `test_the_default_branch_is_read_stripped_from_the_repository`, `test_an_empty_default_branch_is_unreadable_not_guessed` and `test_the_repository_call_failing_is_unreadable`. **The real shape is confirmed.** I ran `gh api repos/FlawlessNa/Legends --jq .default_branch` once, and `od -c` shows the output is `d e v \n`: raw text, not JSON. `FakeGh` answers `movements-improvements\n` in the same shape, and asserts that the arguments are exactly `--jq .default_branch`. |
| 5 | Working-branch holds exactly when base equals `default_branch`; otherwise exit 3, naming both | met | `evaluate` compares `facts.base != facts.default_branch` with `needs_human=True`. The reason reads "Base is feature; only the default branch, dev, is merged by CI." `test_the_working_branch_is_whatever_the_default_branch_is` runs it with four branch names, and `test_a_base_other_than_the_default_branch_names_both` checks that both names appear. |
| 6 | `next <n>` and `model <n>` read the chain from the ticket's own worktree, including from a subdirectory and with the primary on the ticket branch | met | `_ticket_root` → `worktree_for`, which resolves through `governing`. These cli tests check it: `test_the_chain_is_read_from_the_ticket_s_worktree_not_the_session_s` (root and subdirectory, `next` and `model`) and `test_the_primary_checkout_on_the_ticket_branch_is_the_ticket_s_worktree` (root and subdirectory). The worktrees tests cover the primary found from a linked session, and the primary as the session, from its root and from a subdirectory. |
| 7 | None is exit 2 naming `issue/<n>-*`; several is exit 3 naming each; the model table comes from the session's checkout | met | `test_a_ticket_with_no_worktree_is_misuse_and_names_its_branch` covers `next`, `model` and `model --stage qa`. `test_two_worktrees_for_one_ticket_need_a_human_and_name_each` covers the ambiguous case. `load_models(session / TABLE_PATH)`. **Mutation:** I changed that line to `chain_root / TABLE_PATH`, and `test_the_model_table_is_the_session_s_never_the_ticket_s` went red (exit 3 from the ticket's broken table). Then I restored it. |
| 8 | `ticket_worktrees` and `worktree_for` live in `worktrees.py`; `ticket_worktrees` is unchanged; `factory.cli.ticket_worktrees` resolves | met | The function body is moved verbatim (I compared the removed and added hunks line by line). cli.py imports both names. `test_ticket_worktrees_is_the_same_function_the_cli_exports` checks identity. |
| 9 | Two set-equality tests against the document, both red against the old document | met | `test_condition_four_lists_exactly_the_allowed_paths` was red against the old source and old document (`.claude/**` extra, `.factory/**` missing). `test_the_protected_set_section_lists_exactly_the_protected_paths` is red **as "new POLICY, old document"**, which is what `spec-review-2` note b asks for. I ran that state myself: merge.py at HEAD, merge-policy.md at `ac104aa`. The nine module paths showed up as extra. `_path_tokens` keeps only tokens that contain `/` or start with `.`, so the bare `` `factory` `` token is ignored. |
| 10 | merge-policy.md: `.factory/**` is allowlisted and `.claude/**` is not; the workflow is on dev but merges nothing until #151; condition 8 is the default branch; `factory/**` is the protected package | met | Every statement is true against `POLICY`. Condition 4's row equals `allowed_paths`. The protected-set section equals `protected_paths`. The values test still passes. `.github/workflows/merge-policy.yml` exists on local `dev` (`0875d49`). |
| 11 | `factory/AGENTS.md` no longer says to add modules by hand | met | The paragraph now says "A new module is covered the moment it exists; nothing is added by hand." |
| 12 | design.md's R11 and §10 name `dev`; d6 records the fix on 2026-10-22 | met | Lines 38, 98 and 289 of the diff. |
| 13 | `.gitattributes` holds `.factory/** text eol=lf` | met | It is a one-line file ending in `\n`. `git check-attr` reports `text: set` and `eol: lf` for `.factory/217/spec.md`. |
| 14 | The full suite is green; every changed test in test_merge.py and test_cli.py is named in the plan with the behaviour that moved | met | Results: `1240 passed, 3 skipped, 25 deselected`, 0 failed, 0 errors, 0 xfailed (my second run; see finding 6 for the first). Ruff check and format are clean on `factory` and `tests/test_factory`. Pyright reports 0 errors on the six changed Python files. These changes are named in the plan: `_passing`, `FakeGh`, `test_the_document_states_every_condition_and_value`, and the two cli ticket-form tests. `test_hooks.py` and `conftest.py` are unchanged. Nothing was weakened. `FakeGh` grows only additively. The `base="dev"` cases at test_merge.py:200, :215 and :226 still mean "not the default branch", because `_passing` uses `trunk`. |

## The red proof

I reverted only the source and docs to `ac104aa`: merge.py, cli.py,
factory/AGENTS.md, merge-policy.md and design.md. I also removed
`factory/worktrees.py` and `.gitattributes`, and kept the tests as they are at
HEAD.

- **As is:** `test_merge.py` fails to collect (`TypeError: ... unexpected
  keyword argument 'default_branch'`), and `test_worktrees.py` fails with
  `ModuleNotFoundError: No module named 'factory.worktrees'`. The builder
  reported the same.
- **With the inert stub** (`default_branch: str = ""`, last field, read by no
  source): I selected the new and changed tests and got **26 failed, 4 passed**.
  Each failure reproduces the reasons in `plan.md`, line for line.
- **Was the stub honest?** Yes. No source path reads the field, so the stub
  changes no verdict. It only lets the module collect, and each new test fails
  on the old *behaviour*. For example, the old source compares against
  `movements-improvements`, its `gather` never calls the repository endpoint,
  and its payload has no `default_branch` key. I restored everything with
  `git checkout HEAD -- factory docs/factory .gitattributes`, and
  `git status --short` was empty afterwards.

## Findings

1. **The proof's "26 failed" counts a selection, not the module.** It does not
   say so. With the stub, the whole of `tests/test_factory` gives **64 failed,
   238 passed, 1 error**. All 38 extra failures have one cause. `_passing` now
   sets `base="trunk"`, while the old source still requires
   `movements-improvements`, so every "fails alone" test also picks up
   `WORKING_BRANCH`. That follows from the justified `_passing` change, and it
   is not a wrong red. But anyone who reruns the stated recipe on the whole
   module will not see 26.
   *Fix (PR body):* say the 26 came from selecting the new and changed tests.
   Also say that the full module under the stub fails 64, the 38 extras being
   `_passing`'s baseline disagreeing with the old `working_branch`.

2. **One red reason is attributed to the wrong cause.** `plan.md` labels
   `'sonnet' == 'opus'` as "(table read from the ticket's checkout)". The old
   source never looked at the ticket's checkout. It read both chain and table
   from the session, and was red because the chain was missing. The test does
   guard the table property after the change: my mutation above proves it.
   *Fix (PR body):* reword the label to "chain read from the session". The
   table guard is shown by mutation, not by the red run.

3. **The win32 case test does not test what its name says.** Neither does the
   "not by string" property it is meant to cover.
   `test_the_same_directory_spelled_with_another_case_is_one_worktree` passes an
   upper-cased path. `governing` → `_resolved` → `Path.resolve()` turns it back
   into the true case before `worktree_for` compares anything (checked:
   `Path(str(p).upper()).resolve()` returns the on-disk case).
   - I mutated the dedup key to `str(candidate)`, and all 57 worktrees and cli
     tests stayed green.
   - I mutated it to never deduplicate, and 7 went red, including both
     `found_once` cases and the four cli primary-on-ticket cases.

   So spec-review-2 note a is met: the dedup is there and the double count is
   guarded. Whether it compares by `Path` or by string is not checked. The
   implementation (`candidate.resolve()` as a `WindowsPath` dict key) is right.
   *Fix:* either drop the claim in "Could not verify" that this test covers case
   insensitivity, or test the dedup with two candidate spellings that
   `resolve()` cannot merge first. Optional.

4. **No-argument `factory next`, and also `factory model`, now behave
   differently in a subdirectory.** The builder reports this for `next` only.
   - `_next`: before, `current_branch(Path.cwd())` returned `None` in a
     subdirectory, because there is no `.git` there, so it answered "no ticket".
     Now the session root's branch is used.
   - `_model` with no ticket: the same change for the branch. It also loads
     `configs/factory-models.toml` from the worktree root, where a subdirectory
     run used to fail with `TableError`.

   Both look like improvements, and the session-checkout rule from criterion 7
   still holds. But no spec criterion asked for them, and no test pins them.
   *Fix (PR body):* name both commands under "Could not verify" or as
   unspecified behaviour changes.

5. **Nit: one docstring is stale.**
   `test_every_module_the_console_script_imports_is_protected` still says "a new
   import fails here until a person adds it to the protected set". Under
   `factory/**` that can no longer happen for a module inside the package. The
   plan says the test is "unchanged in text", so this is the price of keeping
   it so. Leave it, or fix it in a later ticket that touches the file.

6. **A flaky test outside the radius.** My first full-suite run gave
   `1 failed, 1239 passed`:
   `tests/test_botting/test_typematic_fills.py::test_truncate_lands_exactly_on_the_limit_for_a_multi_step_walk`.
   Called directly 300 times, it failed 30 times (about 10%). This branch does
   not touch that file (last changed in `5d1df4f`). The module passes on rerun,
   and the full rerun was green. It is not this ticket's to fix, but it deserves
   its own issue.

## What I could not verify

- **Real `git worktree add` layouts.** Every worktree test uses `.git`
  structures built by hand (`_primary` and `_linked`). I did not run
  `worktree_for` against a real repository's worktrees.
- **That the workflow token can read `repos/{repo}` in a real
  `pull_request_target` run.** I confirmed the output shape with my own
  credentials only.
- **That the workflow fires on every PR from `dev`.** I saw the file on local
  `dev`. I did not read GitHub's Actions state.
- **That the PR fails working-branch with exit 3 until it is retargeted.** That
  depends on #226's `merge.py` running in CI. I did not observe it.
- **Line endings in the working copy.** 58 `.factory/` files are `w/crlf` in
  this worktree's copy, while the index is all `i/lf`. They were checked out
  before `.gitattributes` existed, and they normalize on the next checkout. I
  did not prove that this has no effect on hooks that read those files in
  place.
- **Nothing here sends keys to the game.** No key or input timing can change.
