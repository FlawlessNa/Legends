---
ticket: 207
stage: design
cycle: 3
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "a ticket worktree's base is the parent of the oldest commit on HEAD's history that touches .factory/<n>/, the intent-and-spec commit the process puts first, and only when no such commit exists is it git merge-base HEAD origin/HEAD, with red tests for a stacked branch, for the default branch moving after the branch was cut, for the branch having been pushed, and for a child branch stacked on it"
---

# Spec review, cycle 3: the base

**Verdict: `pass`.** I checked criterion 1 alone, against `spec.md` at `d7af5e8`.

- **The three holes from cycle 2 are closed.** I probed each against the same
  scratch repository.
- **The stacked case holds** in this worktree.
- **Three notes remain.** One rule change is needed when the default branch is
  merged into a ticket branch: it over-refuses, which is not a hole. There are
  also two edge cases. None lets committed source escape, so the plan can settle
  all three. The plan must settle the first.

## The three holes: closed

The scratch repository from cycle 2: `dev` at `c1`, then `issue/1-x` with:

- `art`, which adds `.factory/1/` and also modifies `a`;
- `src`;
- `src2`.

Then `dev` advanced to `c2` upstream and was fetched. The branch was pushed. A
child `issue/2-child` was cut at `HEAD~1`. The rule:

```
f = git log --reverse --format=%H -- .factory/1/ | head -1    -> art (91d9820)
base = f^                                                    -> c1  (0577400)
diff --name-only base...HEAD, minus .factory/                -> a, src.py, src2.py
```

| Cycle-2 hole | Result |
| --- | --- |
| a. `dev` moved | `src.py` and `src2.py` are both seen. The rule never looks at `origin/HEAD` while a chain commit exists. |
| b. Pushed | Unaffected. No ref is a candidate any more. |
| c. Child branch at `HEAD~1` | Unaffected. Same reason. |

`a`, modified inside the chain commit itself, is counted, because the base is
that commit's *parent*. So source bundled into the intent commit cannot escape
either.

The stacked case: in this worktree,
`git log --reverse --format=%H -- .factory/207/` gives `987af4e`, whose parent is
`016692b`, #217's tip. That matches the spec's claim. On this repository's 857
commits the lookup took 0.10 to 0.15 s, so walking the whole history once per
judged worktree is affordable at Stop.

The residual is source committed before the intent commit. It needs a shell
write, because edit-tool source writes are refused before `spec.md` exists. It is
correctly recorded as `[unenforced]`.

## Notes for the plan

**a. Merging the default branch into a ticket branch sweeps the default branch's
source in.** This over-refuses; it is not a hole, and the plan must settle it.

**Evidence.** In the same scratch branch, I ran `git merge origin/dev` (which
brings `b` from `c2`):

```
cycle-3 rule:  base c1          -> a, b, src.py, src2.py     (b is dev's, not the ticket's)
```

`<base>...HEAD` diffs from the merge-base of `c1` and HEAD, which is `c1`, so
everything merged in since counts. A ticket without a proof is then refused for
the default branch's commits. That is cycle 1's harm in another form.

This is reachable. The repository has 10 "Merge branch 'dev' into ..." merges in
its history. Another reachable case is a stacked ticket bringing in `dev` after
its parent merges.

**Fix.** Take the base as the later of `f^` and `merge-base HEAD origin/HEAD`,
whenever one is an ancestor of the other (`merge-base --is-ancestor`). Otherwise
take `f^`. In the scratch merge, `merge-base HEAD origin/HEAD` is `c2`, and the
change set is `a, src.py, src2.py`: correct.

It also keeps every case above unchanged:

| Case | Base chosen | Why |
| --- | --- | --- |
| Stacked | `f^`, the parent ticket's tip | The default branch's merge-base is older. |
| `dev` moved, not merged | `f^` | The merge-base is `f^` or older. |
| Pushed, child | unchanged | No ref is involved. |

**The plan must** either:

- adopt this refinement, with a red test "default branch merged in after the
  intent commit: its paths are not in the change set"; or
- record the over-refusal as a residual in `stages.md`, with "rebase instead" as
  the workaround.

**b. A chain commit with no parent.** A shallow boundary or a root commit both
give one. `f^` then fails to resolve. The criterion falls back to `merge-base`
only "when no such commit exists", so this case is unassigned. **The plan should**
say that an unresolvable `f^` takes the fallback, and then the no-base path if
that fails too.

**c. A chain that already exists on the default branch.** Two cases:

- a reopened ticket on a fresh branch, where the merged chain is in `dev`'s
  history;
- intent committed in the primary checkout before branching, which `.factory/`'s
  exemption allows.

Either way, `f` lies on the default branch and the base is too old. Note a's
refinement repairs both: the merge-base is then the later of the two. If the
plan does not adopt it, list both as residuals.

## What this review could not verify

- I did not run pytest.
- The refinement in note a was checked on one scratch merge, not by a test.
