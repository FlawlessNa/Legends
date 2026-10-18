---
ticket: 194
stage: design
method: suite
criteria:
  - docs/factory/merge-policy.md states every condition once, each with the reason a failure waits, and docs/factory/README.md links it; a test reads both files and fails when a condition or the link is missing
  - factory merge check <pr> exits 0 only when every condition holds, 3 when any condition a person must settle fails or the facts cannot be read, 1 when the only failures are ones the PR's author can fix, and 2 on a malformed invocation
  - for each condition, a test in tests/test_factory/ constructs facts where only that condition fails and asserts its exit code and the condition it reports
  - every failing condition is reported, not only the first, in prose and under --json
  - a diff touching botting/ is refused with exit 3, proven by a test that needs no network
  - a ticket labelled method:live is refused with exit 3, proven by a test that needs no network
  - a renamed file is judged by its old path as well as its new one, so moving a file out of botting/ is refused with exit 3, proven by a test of the gatherer against recorded gh output
  - a file list shorter than the PR's changed-file count is refused with exit 3, proven by a test of the gatherer against recorded gh output
  - the hard-stop check holds when the path allowlist is widened to every path, proven by a test
  - the self-change check holds when the path allowlist is widened to every path, proven by a test
  - every module the factory console script imports, transitively, is in the protected set, proven by a test that computes the import closure
  - a PR whose head branch lives in a fork is refused with exit 3
  - a draft PR is refused with exit 1
  - a base branch other than the one working branch the policy names is refused with exit 3, dev and main included
  - a required check that has not reported is refused with exit 3; one that is pending or did not succeed is refused with exit 1; one not posted by GitHub Actions does not count
  - the evaluation is one pure function of facts gathered from GitHub; the workflow runs factory merge check and carries no policy condition of its own
  - the workflow triggers on pull_request_target (opened, edited, reopened, synchronize, ready_for_review), on workflow_run of CI completed, and on workflow_dispatch; a test parses the YAML and asserts exactly these
  - the workflow checks out the PR's base branch, never the PR head, with persist-credentials false; no run step interpolates a github.event expression; permissions are declared at the top level and name only what it uses; a test parses the YAML and asserts each
  - the workflow merges only on exit 0, pinned to the evaluated head commit, after re-reading the PR and refusing if its base or head moved; a per-PR concurrency group cancels an evaluation in progress; a test parses the YAML and asserts each
  - the workflow fails its job when the facts could not be read, and passes it when the verdict is wait
  - pytest reports 0 failed, 0 errors, 0 xfailed, and ruff check, ruff format --check and pyright are clean on every touched file
specified_by: claude
specified_at: 2026-10-17
reviewed_by: see spec-review.md
---

# Spec: auto-merge policy

## Source

Issue #194, its body plus Nassim's comment resolving the dependency line (see
`intent.md` → Open questions). The eight conditions are the body's, unchanged.

**Amended after review** (`spec-review.md`, `changes-requested`). The first
version is commit `54eae6d`; `git diff 54eae6d -- .factory/194/spec.md` is the
amendment, and each change traces to a numbered finding.

## Requirements

1. **The policy, stated once**, in `docs/factory/merge-policy.md`: the eight
   conditions from the issue, the additions below, and what a failure means.
   The evaluator's constants carry the values; the doc says which file holds
   them.
2. **The evaluator**, `factory merge check <pr>`: gathers the PR's facts from
   GitHub through `gh`, hands them to a pure function, and reports every
   condition that failed. Exit codes per `factory/AGENTS.md`:

   | Code | When |
   | --- | --- |
   | 0 | Every condition holds. CI may merge |
   | 1 | Only author-fixable conditions failed: the closing reference, a check pending or red, the "Could not verify" section, draft. Fix and re-run |
   | 2 | Malformed invocation |
   | 3 | Anything a person must settle: ticket type, method, paths, hard-stop, self-change, fork, base, a required check that never reported. Also: the facts could not be read, flagged distinctly in the payload |

   When both kinds fail, 3 wins — a person is needed regardless.
3. **The workflow**, `.github/workflows/merge-policy.yml`, runs the evaluator
   from the PR's base branch and merges on exit 0. It carries no condition of
   its own; the policy lives in one place.

## Definitions

- **Closing reference.** After stripping HTML comments from the PR body, a
  case-insensitive match of `close`, `closes`, `closed`, `fix`, `fixes`,
  `fixed`, `resolve`, `resolves` or `resolved`, an optional colon, whitespace,
  then `#<n>`, `<owner>/<repo>#<n>`, or a GitHub issue URL. Condition 1 holds
  when the distinct references are exactly one, it names this repository, and
  it is an open issue rather than a pull request.
- **"Could not verify" section.** A markdown heading whose text starts with
  "Could not verify", up to the next heading of the same or higher level. It is
  non-empty when, after stripping HTML comments, it contains a word character
  and is not solely one of `n/a`, `na`, `none`, `tbd`, `-`.
- **Paths.** Every path the diff touches, including the old path of a rename,
  read from the REST files endpoint, paginated. If the paths read are fewer
  than the PR's changed-file count, the facts are unreadable.
- **Globs** match with `PurePosixPath.full_match`: anchored at the repo root,
  case-sensitive, `*` within one segment, `**` across segments.
- **A required check** is the most recent check run with that exact name on the
  head commit, posted by the `github-actions` app. Green means completed with
  conclusion `success`, nothing else.

## Decisions I made

Each is the conservative reading of something the issue does not settle, and
is repeated in the PR under "Decisions you may want to reverse".

- **The allowlist is the issue's, literally — `.factory/**` is not in it.**
  Every factory PR touches `.factory/<n>/`, so read literally **no factory PR
  can ever auto-merge**, even after #151. Widening the allowlist is risk
  appetite, which is the maintainer's (review finding 3). The narrow reading is
  the one he wrote; the one-line widening is offered in the PR, not taken.
- **The policy never merges a change to itself.** The protected set is
  `docs/factory/merge-policy.md`, `tests/test_factory/test_merge.py`,
  `.github/**`, and every module the `factory` console script imports,
  transitively, with `factory/__main__.py` (review finding 4). Otherwise a
  `type:chore` PR could change the dispatcher, or the allowlist, and merge
  itself. **Consequence:** most `factory/` changes touch `factory/cli.py`, so
  they wait. Recorded as reversible.
- **A fork's PR always waits.** The repository is public; a head in this
  repository means the author has push access.
- **"The working branch" is one named branch**, `movements-improvements`, held
  as a constant. An allowlist of one is stricter than "never `dev` or `main`".
- **Every `type:` label on the ticket must be allowlisted**, and at least one
  present; `method:suite` must be the only `method:` label.
- **The closing reference is parsed from the PR body.** GitHub's
  `closingIssuesReferences` is empty for any base but the default branch
  (checked on #196), and factory PRs target the working branch.
- **Condition 6 reads named checks**: `suite`, `ruff-check`, `ruff-format`,
  `pyright`, posted by GitHub Actions (finding 15). #151 owns producing them,
  from a workflow named `CI`; those names become its commitment. **Until #151
  lands nothing merges** — the policy's own default applied to its own
  precondition.
- **A draft waits** (finding 9), as an author-fixable condition, inside the
  evaluator rather than as a workflow `if:`.
- **CI merges directly rather than enabling GitHub's native auto-merge.** Native
  auto-merge is disabled on the repo and `movements-improvements` has no branch
  protection, so "enable auto-merge" would be refused or would merge without
  any required check.
- **The workflow is `pull_request_target`, and checks out the PR's base branch
  explicitly** (finding 1). Since GitHub's 2025-11-07 change, a
  `pull_request_target` workflow runs from the **default branch's** copy of the
  file and checks out the default branch (`dev` here, which does not contain the
  `factory` package). `workflow_run` always behaved this way. So the evaluator's
  code is the base branch's — the code an agent on the working branch runs
  locally, which is the parity the intent asks for — but **the workflow does
  not fire at all until it reaches `dev`.** That is a handoff, not a
  stop: merging to `dev` is the maintainer's anyway. `on: pull_request` was
  rejected because it runs the PR's own copy of the workflow, which the PR can
  rewrite.
- **The hard-stop list is restated as globs**, each traced to `AGENTS.md`:

  | Glob | `AGENTS.md` item |
  | --- | --- |
  | `botting/controller/**` | Input send path, focus handling, Held-Keys Ledger (ADR 0002: `focused_inputs.py`, `held_keys_ledger.py`) |
  | `maple/model/mechanics/movement_mechanics_v2.py` | ADR 0002: dispatch-time compilation (`MovementHandler`) |
  | `botting/__init__.py`, `botting/logging_config.py`, `botting/telemetry.py` | Telemetry envelope and transport (ADR 0001) |
  | `docs/adr/**`, `docs/agents/typing.md` | Anything an ADR decides: the ADRs, and ADR 0003's ratchet mechanics |
  | `configs/maps/**` | Map JSON |
  | `**/requirements*.txt`, `pyproject.toml`, `.pre-commit-config.yaml` | Pinned dependency versions, including hook revisions |
  | `maple/decision_makers/inventory_manager.py` | Parked |

  `botting/telemetry_events.py` is left off: `AGENTS.md` lists additive Event
  Types as freely changeable.
- **A merge commit, not a squash**, matching every merged factory PR so far.
- **"Wait" passes the workflow; "unreadable" fails it** (finding 11). A red
  cross on every non-allowlisted PR would read as a broken build, but a
  gatherer broken by a `gh` change must not make every PR wait silently.

## Known gaps

- **The hard-stop globs and `AGENTS.md` can drift.** `AGENTS.md` is prose;
  nothing machine-readable is shared until #143. "Anything an ADR decides"
  cannot be expressed as globs in general — every ADR-governed path today is
  covered above, and a new ADR must add its own.
- **Label provenance** (finding 5). Conditions 2 and 3 trust the ticket's
  labels, and an agent acting through the maintainer's `gh` credentials can
  relabel its own ticket. `.claude/**`, where the harness permissions that
  would stop that live, is on the issue's allowlist. Narrowing it is the
  maintainer's call; recorded, not decided.
- **Between evaluation and merge**, ticket labels can change without
  re-triggering. Head and base are re-read; labels are not.
- `specified_by` is the Builder again. The review stand-in is the mitigation,
  and it is not independent the way #163 will make it.

## Verification method: suite

Every condition is a pure function of facts, unit-tested from constructed facts.
The gatherer is tested against recorded `gh` output. The doc and the workflow
are tested by parsing them, so no criterion rests on reading by eye.

What the suite cannot settle, for Could not verify: that GitHub delivers the
events, that the token gets the permissions requested, that `gh` on the runner
returns the recorded shapes, and that any merge happens — which cannot be
observed until the workflow reaches `dev`, #151 lands, and the allowlist admits
`.factory/`.
