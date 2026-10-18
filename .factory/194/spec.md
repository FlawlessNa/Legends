---
ticket: 194
stage: design
method: suite
criteria:
  - docs/factory/merge-policy.md states every condition once, each with the reason a failure waits, and docs/factory/README.md links it
  - factory merge check <pr> exits 0 only when every condition holds, 3 when any condition a person must settle fails, 1 when the only failures are ones the PR's author can fix, and 2 on a malformed invocation
  - every failing condition is reported, not only the first, in prose and under --json
  - a diff touching botting/ is refused with exit 3, proven by a test in tests/test_factory/ that needs no network
  - a ticket labelled method:live is refused with exit 3, proven by a test in tests/test_factory/ that needs no network
  - a renamed file is judged by its old path as well as its new one, so moving a file out of botting/ is refused
  - the hard-stop check holds even when the path allowlist is widened to every path, proven by a test
  - a diff touching the policy itself (merge-policy.md, the evaluator module, its test, anything under .github/) is refused with exit 3
  - a PR whose head branch lives in a fork is refused with exit 3
  - a base branch other than the one working branch the policy names is refused with exit 3, dev and main included
  - the evaluation is one pure function of facts gathered from GitHub; the workflow calls factory merge check and carries no policy condition of its own
  - the workflow never checks out or executes the PR head, and merges only on exit 0, pinned to the head commit that was evaluated
  - pytest reports 0 failed, 0 errors, 0 xfailed, and ruff check, ruff format --check and pyright are clean on every touched file
specified_by: claude
specified_at: 2026-10-17
reviewed_by: see spec-review.md
---

# Spec: auto-merge policy

## Source

Issue #194, its body plus Nassim's comment resolving the dependency line (see
`intent.md` → Open questions). The eight conditions are the body's, unchanged.

## Requirements

1. **The policy, stated once**, in `docs/factory/merge-policy.md`: the eight
   conditions from the issue, the additions below, and what a failure means.
   The evaluator's constants carry the same values; the doc says which file
   holds them, rather than the two drifting.
2. **The evaluator**, `factory merge check <pr>`: gathers the PR's facts from
   GitHub through `gh`, hands them to a pure function, and reports every
   condition that failed. Exit codes per `factory/AGENTS.md`:

   | Code | When |
   | --- | --- |
   | 0 | Every condition holds. CI may merge |
   | 1 | Only author-fixable conditions failed: the closing reference (1), a check not yet green (6), the "Could not verify" section (7). Fix and re-run |
   | 2 | Malformed invocation |
   | 3 | Anything a person must settle: ticket type (2), method (3), paths (4), hard-stop (5), base (8), and the additions below. Also: the facts could not be read at all |

   When both kinds fail, 3 wins — a person is needed regardless.
3. **The workflow**, `.github/workflows/merge-policy.yml`: runs the evaluator
   from the base branch's code on every PR event that can change the answer,
   and merges on exit 0. It carries no condition of its own; the policy lives
   in one place.

## Decisions I made

Each of these is the conservative reading of something the issue does not
settle. All are recorded again in the PR under "Decisions you may want to
reverse".

- **The policy never merges a change to itself.** The allowlist includes
  `factory/**` and `docs/**`, which is where the evaluator and the policy doc
  live. Read literally, a `type:chore` PR could widen the allowlist and merge
  itself — trust widened by an agent, with no human in `git log`. The issue's
  premise is that no agent decides, so `docs/factory/merge-policy.md`,
  `factory/merge.py`, `tests/test_factory/test_merge.py` and `.github/**` always
  wait. `.github/**` is already outside the allowlist; it is named so that
  widening the allowlist cannot reach it.
- **A fork's PR always waits.** The repository is public. Without this, anyone
  could open a PR from a fork closing a `type:chore` ticket, touch `docs/`, and
  have it merged by CI. A head in this repository means the author has push
  access.
- **"The working branch" is one named branch**, `movements-improvements`, held
  as a constant beside the allowlist. The issue says "never `dev` or `main`"; an
  allowlist of one is stricter than a denylist of two, and moving it is the same
  visible edit as widening the paths.
- **Every `type:` label on the ticket must be allowlisted**, and at least one
  must be present. A ticket labelled both `type:chore` and `type:build` waits.
  Likewise `method:suite` must be the ticket's only `method:` label.
- **The closing reference is parsed from the PR body**, with HTML comments
  stripped first so the template's own placeholder never counts. GitHub's
  `closingIssuesReferences` is empty for any base other than the default branch
  (checked on #196), and every factory PR targets the working branch.
- **Condition 6 reads named checks**: `suite`, `ruff-check`, `ruff-format`,
  `pyright`, each needing a successful run on the head commit. A missing check
  is a failed condition. #151 owns producing them, and those names become its
  commitment. **Until #151 lands, condition 6 cannot hold and nothing merges.**
  That is the policy's own default — wait — applied to its own precondition. The
  alternative, running the checks inside this workflow, takes scope Nassim's
  comment explicitly left with #151.
- **CI merges directly rather than enabling GitHub's native auto-merge.** Native
  auto-merge is disabled on the repo, and `movements-improvements` has no branch
  protection, so "enable auto-merge" would either be refused or merge without
  any required check. The evaluator verifies condition 6 itself and the merge is
  pinned to the evaluated commit, which gives the same guarantee without a repo
  setting outside `git log`.
- **The hard-stop list is restated as globs in the evaluator.** `AGENTS.md`
  states it as prose, and no machine-readable copy exists yet (#143 will need
  one too). The globs are the conservative reading: `botting/controller/**`
  (input send path, focus, Held-Keys Ledger), `botting/telemetry.py` and
  `botting/logging_config.py` (ADR 0001's envelope and transport),
  `docs/adr/**`, `configs/maps/**`, `requirements*.txt`, `pyproject.toml`,
  `maple/decision_makers/inventory_manager.py`.
- **A merge commit, not a squash**, matching every merged factory PR so far.
- **A "waiting for a human" result does not fail the workflow.** A red cross on
  every non-allowlisted PR would read as a broken build. The verdict and its
  reasons go to the job summary; only a malformed invocation fails the job.

## Verification method: suite

The evaluation is a pure function of facts — labels, paths, check conclusions,
the PR body, the base and head — so every condition is unit-testable from
constructed facts with no network.

What the suite cannot settle, and goes under Could not verify in the PR: that
GitHub delivers the events, that the token has the permissions the workflow
requests, and that `gh` returns the shapes the gatherer reads. The first real
PR after merge is that test.

## Known gap in this spec

`specified_by` is the Builder again. The review stand-in is the mitigation, and
it is not independent the way #163 will make it.
