---
ticket: 217
stage: design
method: suite
criteria:
  - POLICY.protected_paths holds exactly one factory entry, "factory/**", alongside docs/factory/merge-policy.md, tests/test_factory/test_merge.py and .github/**, and a test fails if "factory/**" is removed
  - every module the console script imports, transitively, is covered by the protected set, as the existing closure test computes, and a factory module the console script does not import is protected too
  - Policy no longer has a working_branch field, and grep -rn movements-improvements over factory/ and docs/factory/ returns only design.md's line 14 (a historical read-against note), design.md's d6 sentence, and hooks.py's comment that the trunk may move
  - PullRequestFacts carries default_branch; gather reads it with gh api repos/<repo> --jq .default_branch, strips the raw output, and raises FactsUnreadable when it is empty or the call fails, each with a test
  - the working-branch condition holds exactly when the base equals default_branch, whatever that branch is called, and fails with exit 3 naming both branches otherwise
  - factory next <n> and factory model <n> read ticket n's chain from that ticket's own worktree, found from the session's worktree root (a subdirectory resolves to its root), including the primary checkout when it is the one on the ticket branch
  - with no worktree for the ticket they exit 2 naming issue/<n>-*, and with more than one they exit 3 naming each, and factory model keeps reading the model table from the session's own checkout, never the ticket's
  - ticket_worktrees and a new worktree_for(repo_root, ticket) live in factory/worktrees.py, ticket_worktrees's behaviour is unchanged, and factory.cli.ticket_worktrees still resolves
  - a test parses condition 4's row of merge-policy.md and asserts its paths equal POLICY.allowed_paths as a set, a second does the same for the protected-set list, and both fail against today's document
  - merge-policy.md states that .factory/** is allowlisted and .claude/** is not, says the workflow is on dev but merges nothing until #151 posts the required checks, says condition 8 is the default branch, and lists factory/** as the protected package
  - factory/AGENTS.md no longer tells anyone to add each module to protected_paths by hand
  - docs/factory/design.md's R11 and §10 name dev for the ruleset, and d6 records that the cause was fixed on 2026-10-22
  - .gitattributes holds ".factory/** text eol=lf"
  - the full suite is green, and every test changed in test_merge.py or test_cli.py is named in the plan with the behaviour that moved
specified_by: claude
specified_at: 2026-10-22
revised_after: spec-review.md (changes-requested, 9 findings)
---

# Spec: protect factory/** as one path, resolve a ticket's own worktree, make merge-policy.md true, and stop naming a branch

## Source

Issue #217, including its fifth section (2026-10-22), and
`docs/factory/design.md` §3 (d2, d5, d6), §5 and §10.

## Shape

- **merge.py.**
  - `protected_paths` loses the nine module entries and gains `factory/**`.
  - `Policy.working_branch` is removed.
  - `PullRequestFacts.default_branch: str` is added.
  - `gather` reads it with `gh api repos/<repo> --jq .default_branch`. The output is **raw text, not JSON** (verified: `dev\n`), so it is stripped, and an empty result raises `FactsUnreadable`.
  - `evaluate` compares `facts.base` with `facts.default_branch`.
  - `check`'s payload gains `default_branch`.
- **worktrees.py** is new.
  - It holds `ticket_worktrees`, moved verbatim.
  - It holds `worktree_for(repo_root, ticket) -> tuple[Path, ...]`, which returns every worktree on an `issue/<ticket>-*` branch:
    1. `repo_root` is first resolved to its worktree root through `factory.hooks.governing`.
    2. The candidates are `ticket_worktrees(root)` plus the primary checkout (the common dir's parent) when its branch names the ticket.
  - cli.py imports both names, so `factory.cli.ticket_worktrees` keeps resolving.
- **cli.py.**
  - `_next` and `_model`, given a ticket, take the chain from the single worktree `worktree_for` returns: none is exit 2, more than one is exit 3.
  - `_model` keeps loading `configs/factory-models.toml` from the **session's** checkout. A ticket branch must not be able to change its own model routing, the same principle as #216.
  - `model --stage S <n>` follows the same rule: the ticket form always needs the ticket's worktree, because overrides read its chain.

## Verification method: suite

**Red tests:**
- `factory/**` is present;
- a factory module the console script does not import is protected;
- working-branch is decided by `default_branch`;
- `gather` reads, strips and refuses an empty default branch, and the repository call failing gives `readable: false`;
- `next` and `model` run from the primary checkout and from a subdirectory;
- the primary checkout on the ticket branch;
- ambiguity gives exit 3;
- the table is read from the session's checkout;
- the two document set-equality tests.

**Changed tests,** named in the plan:
- `_passing` sets `base="trunk"` and `default_branch="trunk"`. Not `"dev"`, so the existing `base="dev"` failure cases at test_merge.py:197, :212 and :223 keep their meaning.
- `FakeGh` answers the repository call with raw `movements-improvements\n` by default, matching the recorded `_VIEW`.
- `test_the_document_states_every_condition_and_value` drops `POLICY.working_branch`.
- `test_the_ticket_form_computes_the_stage_from_the_chain` and `test_a_blocked_chain_needs_a_human_and_says_why` now build a ticket worktree, because the ticket form needs one.

These move because the behaviour moved.

## Decisions I made

- **The default branch is read per PR**, one REST call, so changing it on GitHub changes the policy with no code change.
- **Ambiguity is exit 3, not "first match".** Two worktrees on different `issue/<n>-*` names is possible, and silently picking one would route by accident.

## Recorded for the PR body

- **The branch is stacked on #216 (PR #226).** The workflow runs #226's `merge.py`, which still names `movements-improvements`, so this PR fails working-branch with exit 3. That is the safe direction.
- **After #226 merges,** retarget the PR to `dev`. GitHub does it automatically only if #226's branch is deleted.
- "Closes #217" fires only once the change reaches `dev`.

## Not in scope

- The registry.
- The radius lock.
- `stages.md`'s glob wording (#218).
