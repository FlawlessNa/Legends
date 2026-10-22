---
ticket: 217
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "factory next <n> and factory model <n>, run from the primary checkout, answer from ticket n's own worktree when one exists, and exit 2 naming issue/<n>-* when none does"
---

# Spec review: protect factory/**, resolve a ticket's own worktree, make merge-policy.md true, stop naming a branch

**Verdict: `changes-requested`.** I reviewed `spec.md` at `a3cbef9` against
issue #217 (all five sections), `intent.md`, `design.md` §3 and §10, and the
code. The shape is right. It covers all five sections of the issue, and most
criteria can be decided. Two things need fixing before planning:

- The gh call the spec adds has an output shape that the spec leaves unstated.
- `_model`'s change of root leaves the model table's root and `--stage`
  undecided. It also breaks two `test_cli` tests that the spec does not list.

Findings 1–5 must be fixed. Findings 6–9 are minor. Notes a–c need no change to
the spec.

## 1. The default-branch call's output shape is unspecified, and a fake can hide a broken parser

**Evidence.** I ran `gh api repos/FlawlessNa/Legends --jq .default_branch` once,
read-only. It prints `dev\n` as a raw string, not JSON. I also tried a field the
response does not have (`--jq .nonexistent_field`). That prints only `\n`, not
`null`.

The spec says "gather reads it with one more call" and stops there. Two
implementations are plausible, and the tests can only tell them apart if
`FakeGh` answers in the recorded shape:

- `json.loads(out)`. On real output this raises `ValueError`, which `gather`
  turns into `FactsUnreadable`. Every PR then comes back `readable: false`, and
  the workflow fails every job (merge-policy.yml:102). If `FakeGh` returns
  `json.dumps("dev")`, the suite stays green.
- `out.strip()`. On an empty answer this gives `default_branch=""`. That fails
  `working-branch` with exit 3 and the reason "only  is merged". This is the
  safe outcome, but the wrong label: the fact could not be read, and the module
  docstring says such a fact "is never guessed at".

On the error path the design is sound. `run_gh` raises `FactsUnreadable` itself.
`gather`'s `except (KeyError, TypeError, ValueError)` does not catch it and does
not need to. `check` turns it into `NEEDS_HUMAN`, `readable: false`. The
workflow's token needs only metadata read for `GET repos/{repo}`, and GitHub
grants that implicitly.

**Fix.** Add these to criterion 4, or as a new criterion:

- `gather` strips the output.
- An empty result raises `FactsUnreadable`, and so does a result that contains
  whitespace.
- `FakeGh` answers the repository call with `"<name>\n"`, the shape recorded
  on 2026-10-22.
- Two red tests:
  - the repository call alone failing gives `readable: false`;
  - an empty answer gives `readable: false`.

## 2. `_model`'s table root and the two `test_cli` tests it breaks

**Evidence.**

- The `repo` fixture (test_cli.py:76) is a plain `tmp_path` with no `.git`.
  `test_the_ticket_form_computes_the_stage_from_the_chain` (:152) and
  `test_a_blocked_chain_needs_a_human_and_says_why` (:167) run `model 7` there.
  Under the spec, `worktree_for(tmp_path, 7)` sees `git_dir` return `None`, so
  `ticket_worktrees` returns `()` and both tests exit 2. Neither appears in
  "Changed tests". Criterion 12 defers naming them to the plan, but the spec's
  list reads as complete, and it is not.
- `_model` reads `load_models(repo_root / TABLE_PATH)` (cli.py:173). The spec
  says `_model` "read[s] from `worktree_for(Path.cwd(), n)`". It does not say
  whether only the chain moves, or the table too. That choice matters:
  - If the table moves, the model for a ticket's next stage is read from that
    ticket's own branch. A builder could change it.
  - #216's principle is that the judge's inputs come from the primary, not
    from the worktree being judged.
  - The fixture copies the table into the cwd. So the choice also decides how
    the two rewritten tests are built.

**Fix.**

- State that only the chain is read from the ticket's worktree, and the table
  from the caller's checkout. Or argue the opposite, but say which.
- Name both `test_cli` tests under "Changed tests", with the behaviour that
  moved: a ticket with no worktree is now exit 2. Each gets a ticket worktree
  holding the chain.

## 3. `--stage` with a ticket is unspecified

**Evidence.** `model --stage design 7` today reads `read_chain(cwd, 7)` and
answers even when the chain is absent (cli.py:151–152). The spec covers "when
given a ticket" without saying whether `--stage` is included. If it is, this
form starts exiting 2 when there is no worktree. No test pins either behaviour.

**Fix.** Decide and test it. Two options:

- With `--stage`, the chain comes from the ticket's worktree when one exists,
  and is `None` otherwise. `resolve_model` already treats `None` as "not yet
  knowable".
- Or it is exit 2, as the ticket form is.

## 4. `_passing`'s base name is unpinned, and it decides which existing tests change

**Evidence.** The spec says `_passing` "sets `base` and `default_branch`" without
naming the value, and the red test uses `"dev"`. If `_passing` uses `"dev"`, the
following stop meaning what they say:

- the parametrized case `({"base": "dev"}, Condition.WORKING_BRANCH, 3)`
  (test_merge.py:197);
- `test_every_failing_condition_is_reported_not_only_the_first` (:212);
- `test_a_person_beats_the_author_when_both_are_needed` (:223).

All three use `base="dev"` as the *wrong* base. If `_passing` uses `"main"`
instead, the case at :198 breaks the same way. None of the three is in "Changed
tests".

`FakeGh` raises the same question. `_VIEW["baseRefName"]` is
`movements-improvements`, recorded from #196. Its answer to the repository call
must either match that value, or the recorded view has to change.

**Fix.**

- Pin `_passing` to `base=default_branch=` a name that none of the existing
  cases uses, such as `"trunk"`. The existing cases then stand unedited, which
  is what the issue asks for: "tests that use `movements-improvements` as an
  arbitrary branch name need no change".
- Give `FakeGh` a `default_branch` that defaults to `_VIEW["baseRefName"]`.
- Build the "`gather` reads the default branch" red test as
  `FakeGh(default_branch="dev")` against the recorded base. It should fail
  `working-branch` with exit 3, with both names in the reason.

## 5. `factory/AGENTS.md` goes false and is not in scope

**Evidence.** `factory/AGENTS.md:153–157`, as it stands on this branch, says:

> adding an import to `cli.py` ... fails the suite until the module is added to
> `POLICY.protected_paths`

After this change that is untrue. The intent's affected list and the criteria
do not mention the file.

**Fix.** Add a criterion that `factory/AGENTS.md`'s merge-policy section
describes `factory/**` as the protected package. Add the file to the intent's
affected list, so the plan's radius can include it.

## 6. `worktree_for` from a subdirectory, and the primary on the ticket branch (minor)

**Evidence.** I probed with `python -I -B` against this repository and a scratch
repository.

- **From the primary root:** `ticket_worktrees` finds all six ticket worktrees.
  From the primary checkout it is the right primitive.
- **From `C:\Users\Nassim\code\Legends\factory`:** it returns `[]`. So
  `factory next 217`, run from a subdirectory, would exit 2 with "no worktree"
  although one exists. The hook path already handles this case through
  `governing` (`_session_root`, cli.py:394–397).
- **Primary on `issue/5-x`, asked from a linked worktree on another branch:**
  `ticket_worktrees` returns `()`. The primary is never in
  `<common>/worktrees/`. It is included only when it is the `repo_root` passed
  in.

So the spec's "When the cwd's own branch is that ticket, it is that worktree" is
true only when the cwd is the worktree root. The primary seen from elsewhere is
not covered.

**Fix.**

- `worktree_for` first resolves its argument to the enclosing worktree root:
  the nearest ancestor holding `.git`, as `governing` does. Add a test from a
  subdirectory.
- State that the primary on a ticket branch, seen from another worktree, is
  out of scope (exit 2). Or have `worktree_for` alone also check
  `<common>/HEAD`.
- Leave `ticket_worktrees` verbatim. Widening it changes `_stop_everywhere`,
  which is #207's territory.

## 7. Criterion 3's "as a rule" is a judgement (minor)

**Evidence.**

- `git grep movements-improvements -- factory docs/factory` today returns:
  - `design.md:14` (historical, and kept by the issue);
  - `hooks.py:504` (a comment saying the branch should *not* matter);
  - `design.md:38, 98, 289`;
  - `merge-policy.md:44`;
  - `merge.py:63`.
- The new d6 will probably name the branch in the past tense.

"Names it as a rule" depends on the reader.

**Fix.** Make it decidable. After the change, that grep returns only
`design.md:14`, `hooks.py:504` and the new d6 sentence, or whatever set the plan
lists. The workflow test's ban on the word (test_merge.py:642) is a separate
thing and stays.

## 8. The doc test checks condition 4 only; the protected list keeps the old blind spot (minor)

**Evidence.**

- Criterion 9 requires the page to list `factory/**` as the protected package.
  No test checks that:
  - `factory/**` already appears in backticks in condition 4's row;
  - so `test_the_document_states_every_condition_and_value` passes whatever
    the protected-set section says.
  That is the failure mode the issue names, moved to a different list.
- Criterion 9's "says the workflow is live on dev" can mislead. The workflow is
  on `dev` and fires. But nothing merges until #151 posts the required checks:
  `.github/workflows/` holds only `merge-policy.yml`.

**Fix (optional, cheap).**

- Have the two-way test also parse the protected-set bullets, asserting set
  equality with `POLICY.protected_paths`.
- Word criterion 9 as "on `dev` and running", and keep item 2 of "What is live
  today".
- Optionally, say that `factory/**` is allowlisted *and* protected, so in effect
  it never auto-merges.

## 9. "Taking the first is conservative" overclaims (minor)

**Evidence.** Seven worktrees exist today, several for merged tickets.

- Two worktrees on the same branch name is impossible, as the spec says.
- Two worktrees on different `issue/<n>-*` names is possible.
  `worktree_for` would then silently route on whichever sorts first. It only
  reads, but routing on the wrong chain still sends an agent to the wrong
  stage.

**Fix.** Either return exit 3 naming both worktrees when more than one matches,
or keep first-match and say plainly that ambiguity goes undetected.

## Notes, not findings

**a. Removing `Policy.working_branch` breaks nothing else.**

- `git grep working_branch` finds it only in:
  - `merge.py` (lines 44, 63, 408 and 412);
  - `test_merge.py:75` and `:662`;
  - the spec.
- The workflow never reads it. It reads `.readable`, `.head_sha` and `.base`
  from the payload (merge-policy.yml:102–108).
- `Policy` is built once, by keyword, and tests use `replace`.
- `PullRequestFacts` is built in exactly two places: `gather` and `_passing`.

**b. The stacked base needs no spec change, but it needs a handoff line.**

- **Who decides.** For this PR, the workflow on `dev` checks out the base,
  `issue/216-hook-main-checkout`, and runs that branch's `merge.py`. That code
  still has `working_branch="movements-improvements"`, so it fails
  `working-branch` with exit 3, as well as `not-self-change` and
  `paths-allowed`. That is safe.
- **Closing.** "Closes #217" fires only once the change reaches `dev`.
- **Retargeting.** After #226 merges, the PR must be retargeted to `dev`.
  GitHub does this only if #226's head branch is deleted. Otherwise the PR
  would merge into a stale branch.
- **Rebasing.** #216 changed `cli.py` around `ticket_worktrees`. Any further
  change to #226 means rebasing this branch.

Put the retarget step in the PR body's handoff.

**c. Swapping the issue's `gh repo view --json defaultBranchRef` for REST
`repos/<repo>` is fine.** It matches the other REST calls in `gather`, and
criterion 4 names it explicitly.

## What this review could not verify

- That `GET repos/{repo}` succeeds with the workflow's `GITHUB_TOKEN` in a real
  `pull_request_target` run. I inferred it from GitHub's implicit metadata
  permission, and did not observe it.
- How `.gitattributes` with `eol=lf` interacts with existing CRLF working copies
  under `core.autocrlf=true`. I did not probe it. Criterion 11 checks only the
  file's content.
- I did not run pytest. The test breakages in findings 2 and 4 come from reading
  the code, not from running it.
