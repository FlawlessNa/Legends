---
ticket: 194
verdict: changes-requested
reviewed_by: explore-subagent (read-only, no write access)
reviewed_at: 2026-10-17
transcribed_by: claude
---

# Spec review: #194

Produced by a read-only agent that could not edit anything. It was given
`intent.md`, the first version of `spec.md` (`54eae6d`), stage 2 of `stages.md`,
the `spec.md`/`spec-review.md` contracts and `AGENTS.md` → What you may change,
and told not to read any implementation. It was spawned by the Builder, so it
is not independent in the sense #163 will provide.

`reviewed_by` differs from `specified_by` (`claude`) by role, not by model:
the same model, a separate read-only context. That is the gap `spec.md` already
names.

## Disposition

| # | Finding, in short | Done |
| --- | --- | --- |
| 1 | Trigger and ref unspecified | **Acted on.** Confirmed GitHub's 2025-11-07 change: `pull_request_target` runs the default branch's workflow file. Criteria now name the trigger and the base-branch checkout; "does not fire until it reaches `dev`" is a handoff, not a stop, because evaluator parity holds through the base checkout |
| 2 | Script injection | **Acted on.** Criterion: no `github.event` expression in `run:`, `persist-credentials: false`, top-level permissions, proven by parsing the YAML |
| 3 | `.factory/**` not in the allowlist | **Not decided — handed back.** Risk appetite is the maintainer's. Implemented literally; batched into the PR under "Decisions you may want to reverse" per README → Decide and record, not asked mid-session |
| 4 | Self-change protects the module, not its closure | **Acted on.** Protected set is the console script's transitive import closure, proven by a test that computes it |
| 5 | Label provenance; `.claude/**` | **Not decided — recorded** as a known gap in `spec.md` and in the PR |
| 6 | Gatherer untested: truncation, renames, fork | **Acted on.** Two gatherer criteria against recorded `gh` output; fork read from `isCrossRepository` |
| 7 | Race between evaluation and merge | **Acted on** for head and base (re-read before merge, per-PR concurrency). Labels remain a recorded gap |
| 8 | Re-evaluation events unspecified | **Acted on.** Exact events in a criterion, proven by parsing the YAML |
| 9 | Drafts | **Acted on.** Author-fixable condition inside the evaluator |
| 10 | Hard-stop globs unfaithful | **Acted on.** Each glob traced to an `AGENTS.md` item; lockfile set widened to what exists (`**/requirements*.txt`, `.pre-commit-config.yaml`); matcher specified; drift recorded as a known gap |
| 11 | 1-vs-3 mislabels two cases | **Acted on.** A check that never reported is 3; unreadable facts fail the job |
| 12 | Conditions 1, 2, 6, 7 untested; grammar undefined | **Acted on.** One test per condition; closing-reference grammar and "non-empty" defined in `spec.md` |
| 13 | Parity has no criterion | **Acted on** through finding 1: CI runs `factory merge check` from the base branch's code |
| 14 | `method: suite` misfits three criteria | **Acted on.** The doc and the workflow are tested by parsing them |
| 15 | Check provenance | **Acted on.** Only check runs from the `github-actions` app count |

## The review, verbatim

**Verdict: `changes-requested`**

### What it checked

I read `.factory/194/intent.md` against `.factory/194/spec.md`. I also used
three references: the "2 · Design" section of `docs/factory/stages.md`, the
`spec.md` and `spec-review.md` contracts in `docs/factory/artifacts.md`, and the
"What you may change" hard-stop list in `AGENTS.md`. I traced every front-matter
criterion back to the intent, tested each one for decidability and for whether
`method: suite` fits it, checked each "Decisions I made" entry against the
maintainer's four reserved decisions, checked the exit-code split, and compared
the hard-stop globs with the prose they restate. I also looked for
implementations that would meet every criterion and still let something merge
that the intent says must wait. I did not read any Python, workflow file, ADR or
`factory/AGENTS.md`, so claims about where code lives are marked unverified.

The pure-function core is well specified. The gaps are around it: the workflow
trigger, the code that gathers facts from GitHub, and the edges of the
self-change rule. The suite cannot see any of these, and several of them let a
conforming implementation defeat the intent.

### Findings

1. **The workflow trigger is not specified, and both obvious choices break a
   criterion or a constraint.** Requirement 3 says "runs the evaluator from the
   base branch's code", but no criterion names the trigger or says which ref
   the workflow *definition* comes from.
   - With `on: pull_request`, GitHub runs the workflow file from the PR's own
     merge ref. A same-repo PR can rewrite `.github/workflows/merge-policy.yml`
     to skip the evaluator and merge itself. The `.github/**` self-change
     refusal never runs, because the PR replaced the thing that would refuse it.
   - With `on: pull_request_target`, my understanding is that since GitHub's
     late-2025 change the workflow file and checkout ref always come from the
     **default** branch, not the PR's base. Every factory PR targets
     `movements-improvements`, which the spec implies is not the default branch
     (the `closingIssuesReferences` note). If that is right, the workflow does
     nothing until it reaches the default branch, CI runs different evaluator
     code from `factory merge check` on the working branch, and the intent's
     constraint "The local check and CI must give the same answer" fails.
   - **Fix:** confirm GitHub's current `pull_request_target` semantics before
     building. Add a criterion naming the trigger and the exact ref the workflow
     and evaluator code are loaded from, and make it consistent with the
     local-check parity constraint. If parity can't hold on a non-default base,
     that is a stop-and-hand-back, not a decision.

2. **Nothing forbids script injection in the workflow.** A
   `pull_request_target`-style workflow holds a write token, and fork PRs
   trigger it before the evaluator refuses them. Interpolating
   `${{ github.event.pull_request.body }}`, `.title` or `.head.ref` into a
   `run:` step lets any fork author run arbitrary code with `contents: write`.
   "Never checks out or executes the PR head" does not cover this: the payload
   arrives through event fields, not a checkout.
   - **Fix:** add a criterion that no `run:` step interpolates any
     `github.event.*` field, and that values reach scripts through `env:`.
     Require a top-level minimal `permissions:` block and
     `persist-credentials: false` on checkout. Prove all of this with a test
     that parses the YAML.

3. **`.factory/**` is not in the allowlist, so under a literal reading the
   policy refuses every factory PR permanently.** Stage 2 says
   `.factory/<n>/spec.md` is "committed with `intent.md` before any source
   change", so every factory PR touches `.factory/<n>/`. The issue's allowlist
   names `factory/**` (the package), not `.factory/**`. The spec neither
   notices this nor says whether the policy is meant to be inert even after
   #151.
   - Whether to add `.factory/**` widens the path allowlist. That is **risk and
     trust appetite, which belongs to the maintainer**. The Specifier may not
     decide it either way.
   - **Fix:** hand it back to Nassim as an explicit question, and record
     whichever answer he gives in the spec, quoting him.

4. **The self-change exclusion protects the evaluator module, not the code the
   verdict actually depends on.** Protected today:
   `docs/factory/merge-policy.md`, `factory/merge.py`,
   `tests/test_factory/test_merge.py`, `.github/**`.
   - Unprotected: the `factory` CLI dispatcher that maps `merge check` to an
     exit code, any shared `gh`/JSON helper, and any other in-repo module
     `factory/merge.py` imports.
   - A `type:chore` PR changing the dispatcher to always return 0 passes the
     base-code evaluation, because that change isn't in the protected list. It
     merges, and every later PR merges too. That is trust widened by an agent
     with no human in `git log`, which is exactly what the decision says it
     prevents.
   - "The evaluator module" in criterion 8 is also ambiguous.
   - **Fix:** define the protected set as `factory/merge.py`, its transitive
     in-repo import closure, the CLI entry point, the policy doc, its tests and
     `.github/**`. Add a test that computes the import closure and asserts
     every module in it is protected, plus a test that self-change refusal
     still holds when the allowlist is widened to every path (the same shape as
     criterion 7).

5. **Label provenance is unchecked, and the only thing stopping an agent from
   relabelling its ticket can itself be merged.** Conditions 2 and 3 trust the
   ticket's `type:`/`method:` labels. Agents act through the maintainer's `gh`
   credentials, so the only barrier to an agent adding `type:chore` to its own
   ticket is the harness permission rules in `.claude/**`, and `.claude/**` is
   on the allowlist.
   - The chain: an agent PR loosens `.claude/settings*.json` and merges. A
     later agent relabels its own ticket. The ticket's trust class is now an
     agent's choice, not a commit someone decided.
   - Removing `.claude/` enforcement files from the allowlist would narrow the
     issue's stated appetite. That is the maintainer's call, so the spec may
     not quietly decide it.
   - **Fix:** raise it with Nassim, and at minimum record it in the spec as a
     known gap.

6. **The fact gatherer is untested, and it is where the real holes are.** Every
   suite criterion runs the pure function on constructed facts, so an
   implementation passes all of them while the gatherer:
   - **Truncates the file list.** GraphQL `files` pages at 100; REST
     `pulls/{n}/files` caps at 3000. A `botting/` file on page 2 is never seen,
     and the PR merges.
   - **Misses renames.** `gh pr view --json files` does not, as far as I know,
     return `previous_filename`. REST does. Criterion 6 is then satisfied in a
     unit test and false in production.
   - **Decides fork status wrongly**, e.g. by branch name instead of head
     repository.
   - Separately, criterion 6 gives no exit code and no "proven by a test"
     clause, unlike criteria 4 and 5.
   - **Fix:** add criteria that an incomplete or truncated file list exits 3;
     that renames and deletions are judged by every path they touch, with
     exit 3; and that the gatherer is tested offline against recorded
     `gh`/REST JSON fixtures, including a paginated file list and a rename.

7. **There is a race between evaluation and merge on everything except the
   head commit.** `--match-head-commit` pins the head commit only. Between
   evaluation and merge, the base can be retargeted (e.g. to `main`), the body
   edited, or ticket labels changed. A merge into whatever the PR's base is at
   that moment would then land in `main`. The window is short and needs push
   access, but agents have push access.
   - **Fix:** add a criterion requiring a per-PR `concurrency` group with
     `cancel-in-progress`, and a re-read of base and head immediately before
     the merge call, refusing on any change. Or merge through an API call that
     also asserts the base.

8. **The re-evaluation events are unspecified, so a PR can satisfy every
   condition and never merge.** "Every PR event that can change the answer" is
   not decidable. Condition 6's checks usually finish *after*
   `opened`/`synchronize`. Unless check completion (`check_suite`/`workflow_run`
   from #151's workflow) re-triggers evaluation, an eligible PR waits forever.
   That is safe, but it defeats the outcome. `edited` (body, base), `reopened`
   and `ready_for_review` are also needed.
   - **Fix:** add a criterion listing the exact events, proven by the
     YAML-parsing test.

9. **Draft PRs are not handled.** A draft that meets all eight conditions is
   merged by CI. Skipping drafts with an `if:` in the YAML would break
   criterion 11 ("carries no policy condition of its own").
   - **Fix:** add "PR is not a draft" as an author-fixable condition (exit 1)
     inside the evaluator. This is conservative narrowing, which is the
     Specifier's to decide.

10. **The hard-stop globs are not a faithful reading of `AGENTS.md`.**
    - **"Anything an ADR decides"** became `docs/adr/**`, which protects the
      text of the ADRs, not the code they govern. Today's allowlist already
      keeps `botting/` and `maple/` out, so this is the only hard-stop item
      that matters now: code governed by an ADR that lives under `factory/`,
      `docs/`, `.claude/` or `tests/test_factory/` is unprotected. **Fix:** map
      each ADR to the paths it governs, citing the ADR, or state that this
      hard-stop cannot be expressed as globs and record it as a known gap.
    - **`botting/controller/**`** is claimed to cover the input send path,
      focus handling and the Held-Keys Ledger. The spec gives no evidence, and
      focus handling in particular may live elsewhere. **Fix:** cite ADR 0002,
      or the files, for each path.
    - **Pinned dependency versions** is missing lockfiles (`uv.lock`,
      `poetry.lock`), `constraints*.txt`, `**/requirements*.txt` in
      subdirectories, `setup.cfg`/`setup.py`, and `.pre-commit-config.yaml`
      (pinned hook revisions). **Fix:** add them.
    - **Glob semantics are unspecified**: anchored at the repo root or not,
      whether `*` crosses `/` (Python's `fnmatch` lets it), and case
      sensitivity. The repo is developed on Windows. **Fix:** specify the
      matcher and test those edge cases.
    - **Drift:** `AGENTS.md` and the evaluator constants will drift silently.
      **Fix:** record it as a known gap until a machine-readable list exists
      (#143).

11. **The 1-versus-3 split mislabels two cases.**
    - A **missing named check** is filed under condition 6 as exit 1 ("fix and
      re-run"). Until #151 lands, no author can fix it, so every PR gets an
      instruction it cannot follow. **Fix:** a missing check exits 3, or at
      least reports a distinct reason; a pending or failed check stays 1.
    - **"Facts could not be read"** is exit 3, and the workflow stays green on
      3. A gatherer broken by a `gh` output change therefore makes every PR wait
      quietly and never shows up anywhere, and that is the very thing the spec
      puts under "Could not verify". **Fix:** read failures fail the job,
      through a distinct exit code or reason that the workflow treats as an
      error.
    - With those two fixed, the split is coherent and decidable:
      person-settled beats author-fixable, and the classification is a fixed
      table.

12. **Conditions 1, 2, 6 and 7 have no test-backed criterion, and two of them
    are not decidable as written.**
    - "Closes exactly one ticket" has no grammar: which keywords
      (close/closes/closed/fix/fixes/fixed/resolve/resolves/resolved), whether
      matching ignores case, whether the colon is optional, and how cross-repo
      `owner/repo#n` and URL forms are treated.
    - Nothing requires the referenced number to be an **open issue in this
      repository** rather than a PR or a closed issue.
    - "Present and non-empty" for "Could not verify" leaves open whether `-`,
      `n/a`, or a section that is nothing but an HTML comment counts.
    - **Fix:** add one criterion: "for each condition, a test in
      `tests/test_factory/` constructs facts where only that condition fails
      and asserts its exit code and reported reason". Define the
      closing-reference grammar and "non-empty" (after stripping HTML comments
      and whitespace, at least one character remains) in the body. Optionally
      cross-check the ticket's `method:` label against `.factory/<n>/spec.md`.

13. **The intent constraint "The local check and CI must give the same answer"
    has no criterion.** Criterion 11 covers only the "no condition in the YAML"
    half.
    - **Fix:** add a criterion that the workflow runs the same
      `factory merge check <pr>` command, from code at the same commit an agent
      would run locally. This depends on how finding 1 is resolved.

14. **`method: suite` does not fit three criteria as written.**
    - Criterion 1 (doc states each condition, README links it) is a
      documentation-presence check.
    - Criteria 11 and 12 are properties of a YAML file.
    - Pytest settles none of them unless a test reads those files.
    - **Fix:** require tests that parse `merge-policy.md` (each condition and
      each constant present, the README link present) and the workflow YAML
      (trigger, events, no head checkout, `--match-head-commit`, no
      `github.event.*` in `run:`, permissions). Otherwise name them explicitly
      as review-checked. The parts that are truly unverifiable offline are
      already listed under "Could not verify": event delivery, token
      permissions, and an actual merge. Add one more: no merge can be observed
      until #151 lands.

15. **Check provenance (minor).** Matching checks by name alone lets any token
    with `statuses:write` or `checks:write` post a green `suite`.
    - **Fix:** also require the check run's app to be GitHub Actions.

**On "Decisions I made":** none of them widens appetite.
- The self-change exclusion, fork refusal, the single named working branch,
  all-`type:`-labels-allowlisted, sole-`method:suite`, and "nothing merges
  until #151" all narrow. Each implements a stated part of the intent: no agent
  decides, widening is a commit, the default is to wait. The intent explicitly
  gave the #151 question to `spec.md`.
- "Merge commit, not squash" and "a wait does not fail the workflow" are the
  stage's to decide. Finding 11 qualifies the second.
- The overstep is by **omission**: findings 3 and 5 are appetite questions
  reserved to the maintainer, and the spec either missed them (`.factory/**`)
  or was silent (`.claude/**` enforcement files). Both must be handed back, not
  decided.

### Criteria it judged sound

> "a ticket labelled method:live is refused with exit 3, proven by a test in
> tests/test_factory/ that needs no network"

Decidable: one constructed input, one expected exit code, one named test
location, and an offline constraint anyone can check by running pytest with the
network cut. Two honest people cannot disagree about whether it was met.

> "the hard-stop check holds even when the path allowlist is widened to every
> path, proven by a test"

Decidable, and it is the best criterion in the spec, because it turns the
intent's "holds under any circumstances, independently of the path allowlist"
into an executable assertion: set the allowlist to `**`, feed a hard-stop path,
assert refusal.

> "a base branch other than the one working branch the policy names is refused
> with exit 3, dev and main included"

Decidable: a finite set of named inputs with a fixed expected outcome.

> "pytest reports 0 failed, 0 errors, 0 xfailed, and ruff check,
> ruff format --check and pyright are clean on every touched file"

Decidable, mechanically checkable.
