---
ticket: 217
stage: design
cycle: 2
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "a test parses condition 4's row of merge-policy.md and asserts its paths equal POLICY.allowed_paths as a set, a second does the same for the protected-set list, and both fail against today's document"
---

# Spec review, cycle 2: protect factory/**, resolve a ticket's own worktree, make merge-policy.md true, stop naming a branch

**Verdict: `pass`.** I checked only the nine findings from `spec-review.md`,
against `spec.md` at `0ba765f`. All nine are resolved at the level of the
criteria. Two notes remain. One is a bug in the Shape's sketch of
`worktree_for`, which I reproduced. The other is a red claim that holds only
under one reading. Neither changes what a criterion requires, so the plan can
settle both. Both must be settled there.

## 1. The default branch's output shape: resolved

Criterion 4 now says `gather` uses `gh api repos/<repo> --jq .default_branch`,
"strips the raw output, and raises FactsUnreadable when it is empty or the call
fails, each with a test". The Shape records the verified `dev\n`. Under Changed
tests, `FakeGh` answers in raw text. I had suggested refusing output that
contains whitespace. Stripping makes that unnecessary.

## 2. The table root and the two `test_cli` tests: resolved

Criterion 7 says `factory model` "keeps reading the model table from the
session's own checkout, never the ticket's". The reason given is #216's. Both
tests are named under Changed tests, each with the behaviour that moved: the
ticket form needs a worktree.

## 3. `--stage` with a ticket: resolved

It follows the same rule as the ticket form. Without a worktree it is exit 2. That
changes behaviour: today `model --stage S <n>` answers with no chain. No
existing test pins the old behaviour. The PR body should name the change.

## 4. `_passing`'s base name: resolved

`_passing` uses `"trunk"` for both fields. The spec explains why: the `base="dev"`
cases at :197, :212 and :223 keep their meaning. `FakeGh` defaults to the
recorded `movements-improvements`, so `_VIEW` is unchanged.

## 5. `factory/AGENTS.md`: resolved

A new criterion: "factory/AGENTS.md no longer tells anyone to add each module to
protected_paths by hand". The intent's affected list still omits the file. That
is harmless, as long as the plan's radius includes it.

## 6. `worktree_for`: resolved in the criteria; the Shape double-counts the primary

Criteria 6 and 7 are right as written:

- a subdirectory resolves to its root;
- the primary checkout is included when it is the one on the ticket branch;
- none is exit 2, and more than one is exit 3.

`hooks.py` imports only from `factory.chain`, so the new import of `governing`
creates no cycle.

**Note a: the Shape, followed literally, breaks criterion 6.** The Shape builds
the candidates as "`ticket_worktrees(root)` plus the primary checkout (the
common dir's parent) when its branch names the ticket". When the session *is*
the primary, and the primary is on the ticket branch, `ticket_worktrees`
already includes it as `repo_root`. Adding the primary again counts it twice,
and two candidates trip the exit-3 rule.

I reproduced this with `python -I -B` in a scratch repository: a primary on
`issue/5-x`, a linked worktree on `scratch`, and that composition built from
`governing`, `ticket_worktrees` and `git_dir`.

| Run from | Result |
| --- | --- |
| primary | the primary, twice |
| `primary/sub` | the primary, twice |
| linked | the primary, once (correct) |

So "found from the session's worktree root ... including the primary checkout"
would answer exit 3 in the very case the criterion names.

The paths come back in different forms: `resolve()` returned a lower-case
drive-relative segment where the gitdir file has upper case. Deduplicating by
`Path` equality still works, because `WindowsPath` compares case-insensitively.
Deduplicating by string would not.

**The plan must:**

- deduplicate the candidates by `Path` equality;
- add a test with the session being the primary on the ticket branch, run
  both from its root and from a subdirectory. It must answer, not exit 3.

## 7. "As a rule": resolved

Criterion 3 now lists the grep hits allowed to remain:

- design.md line 14;
- the d6 sentence;
- the comment in `hooks.py`.

That can be checked mechanically.

## 8. The doc tests and the "live" wording: resolved, with one red claim to settle

Two changes, both resolved:

- A second set-equality test covers the protected list.
- Criterion 10 now says the workflow "is on dev but merges nothing until #151
  posts the required checks".

**Note b: the second test is not red against today's document under today's
`POLICY`.** The criterion says "both fail against today's document". I compared
today's protected-set section with today's `POLICY.protected_paths`. The only
difference is the token `` `factory` ``, from "the `factory` console script",
which sits in the second bullet itself. Read as paths, the two sets are equal.

So the second test goes red against today's document only in two cases:

- under the new `POLICY`, with the document change stashed and the
  `merge.py` change kept;
- through a parser artefact: picking up that bare `` `factory` `` token.

The condition-4 test has no such problem. It is red against today's document
under either `POLICY`.

**The plan must:**

- state the second test's red as "new `POLICY`, old document", or not claim
  red for it at all, since it is a guard;
- make the parser take only path-like tokens, so that the bare `` `factory` ``
  token never makes it pass or fail.

## 9. Ambiguity: resolved

More than one matching worktree is exit 3, and each one is named. The decision is
recorded with its reason.

## What this review could not verify

- I did not run pytest.
- The double count in note a is reproduced against a composition of today's
  functions, not against an implementation, because none exists yet.
- What I said in cycle 1 still stands: the workflow token's read of
  `repos/{repo}` in a real `pull_request_target` run is inferred, not observed.
