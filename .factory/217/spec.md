---
ticket: 217
stage: design
method: suite
criteria:
  - POLICY.protected_paths holds exactly one factory entry, "factory/**", alongside docs/factory/merge-policy.md, tests/test_factory/test_merge.py and .github/**, and a test fails if "factory/**" is removed
  - every module the console script imports, transitively, is covered by the protected set, as the existing closure test computes, and a factory module the console script does not import is protected too
  - Policy no longer has a working_branch field and no file under factory/ or docs/factory/ names movements-improvements as a rule
  - PullRequestFacts carries default_branch, gather reads it from GitHub (repos/<owner>/<repo> .default_branch), and the working-branch condition holds exactly when the base equals it, whatever that branch is called
  - a PR whose base is not the default branch fails working-branch with exit 3, and the reason names both branches
  - factory next <n> and factory model <n>, run from the primary checkout, answer from ticket n's own worktree when one exists, and exit 2 naming issue/<n>-* when none does
  - ticket_worktrees and a new worktree_for(repo_root, ticket) live in factory/worktrees.py, and factory.cli.ticket_worktrees still resolves
  - a test parses condition 4's row of merge-policy.md and asserts its paths equal POLICY.allowed_paths as a set, and fails against today's document
  - merge-policy.md states that .factory/** is allowlisted and .claude/** is not, says the workflow is live on dev, says condition 8 is the default branch, and lists factory/** as the protected package
  - docs/factory/design.md's R11 and §10 name dev for the ruleset, and d6 records that the cause was fixed on 2026-10-22
  - .gitattributes holds ".factory/** text eol=lf"
  - the full suite is green, and every test changed in test_merge.py or test_cli.py is named in the plan with the behaviour that moved
specified_by: claude
specified_at: 2026-10-22
---

# Spec: protect factory/** as one path, resolve a ticket's own worktree, make merge-policy.md true, and stop naming a branch

## Source

Issue #217, including the fifth section added on 2026-10-22, and
`docs/factory/design.md` §3 (d2, d5, d6), §5 and §10.

## Shape

- **merge.py.**
  - `protected_paths` loses its nine module entries and gains `factory/**`.
  - `Policy.working_branch` is removed.
  - `PullRequestFacts.default_branch: str` is added.
  - `gather` reads it with one more call: `gh api repos/<repo> --jq .default_branch`.
  - `evaluate` compares `facts.base` with `facts.default_branch`.
  - `check`'s payload gains `default_branch`.
- **worktrees.py** is new. It holds `ticket_worktrees`, moved verbatim from cli.py, and `worktree_for(repo_root, ticket) -> Path | None`: the first worktree whose branch names the ticket. cli.py imports both, so `factory.cli.ticket_worktrees` keeps resolving and test_cli's import is unchanged.
- **cli.py.** `_next` and `_model`, when given a ticket, read from `worktree_for(Path.cwd(), n)`. When the cwd's own branch is that ticket, it is that worktree. With no worktree, they exit 2 with "no worktree on issue/<n>-*".

## Verification method: suite

- **Red tests:**
  - `factory/**` present;
  - a non-imported `factory/` module protected;
  - working-branch decided by `default_branch` (`base="dev"`, `default_branch="dev"` passes; `base="movements-improvements"` fails);
  - `gather` reads the default branch;
  - `next`/`model` from the primary checkout;
  - the two-way doc test.
- **Changed tests,** named in the plan:
  - `_passing` sets `base` and `default_branch`, not `POLICY.working_branch`;
  - `FakeGh` answers the repository call;
  - `test_the_document_states_every_condition_and_value` drops `POLICY.working_branch` from its values.

  These move because the behaviour moved, not as a refactor.

## Decisions I made

- **The default branch is read per PR, not cached in config.** It is one REST call, and changing the default branch on GitHub then changes the policy with no code change. That is the "no special branch" property.
- **`worktree_for` picks the first match.** Two worktrees on one ticket's branch is not a state git allows for the same branch name. Two different `issue/<n>-*` names would be a mistake, and taking the first is conservative because routing only reads.

## Not in scope

- The registry (dropped in the design).
- The radius lock.
- `stages.md`'s glob wording (#218).
