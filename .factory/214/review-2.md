---
ticket: 214
stage: review
cycle: 2
verdict: pass
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 0dde478270ad7590d59af52f114a129cc64f295f
---

# Review, cycle 2: commit the agreed factory design

**Verdict: `pass`.** This cycle checks only the eight findings in
`review.md`, against `0dde478` (`git diff 1e42d7a 0dde478`). All three
blocking-level folds are now resolved, and `design.md` no longer contradicts
itself on `.claude/`. Criteria 4 and 10 are now met. Four small points remain
open: one new (finding A) and three left over. None affects a criterion, so
none blocks.

## Cycle 1, finding by finding

| # | Cycle-1 finding | Now |
| --- | --- | --- |
| 1 | X4 not in §4 rule 2 | **Resolved.** Rule 2 runs the per-path rules "except `.claude/` files", which go to `hooks_disabled` (§7, last row). §4 and §7 now agree. |
| 2 | X5 not in §9 OpenPR; hard-stop half lost | **Resolved.** §9's OpenPR list checks `base_sha...HEAD` against `acceptance.radius` and `hard_stop_approved`, failing closed, before it pushes. The §7 radius row restores "hard-stop paths not in `hard_stop_approved`" and adds "and the hard-stop list" to the base-diff check. This now agrees with #222 and #159. One leftover: the §9 `accept` exit-1 cell still says only "the base diff is outside the radius" (open point 1). |
| 3 | X3: no re-check after the proof | **Resolved.** §4 rule 3 asserts HEAD and `status --ignored`, and "the same assertion follows every proof run". This agrees with #145 and #159. |
| 4 | §5 `roles.py` against #218 | **Resolved.** §5 names the designer as the only `own-worktree` role. #218's body on GitHub (read 2026-10-22) now has the same enum. Its accept row also requires a match with the loop's acceptance record in `state.json`, so the coordinator note is settled too. The `blob()` signature nit was not taken (open point 3). |
| 5 | §13 lost the How column | **Resolved.** Both tables have a How column, and a legend precedes them. B3 reads "taken" and X1 reads "changed", as criterion 5 requires. Labels agree with the source, or follow the folds (m7 "changed" is two tables; c "changed" is the decided staleness rule). One leftover: the legend says a *changed* row "says how", but M8 ("R6; §11") and m6 ("R2") do not (open point 2). |
| 6 | §12 dropped the `python -I` item | **Resolved**, with a new problem in its wording (finding A). |
| 7 | `CONTEXT.md` house style | **Resolved.** Both entries use the inline form, `_Avoid_: X — reason; Y — reason.`, wrapped as other entries wrap. **I agree with keeping the four-term preamble as a list.** It scopes words for the section rather than defining an entry, and no `_Avoid_` line is involved. The "same on-disk state" nit is unchanged (open point 4). |
| 8 | Nits | **Resolved.** `.gitattributes` is future tense, attributed to #217, and stated as absent at `4296edc` (true). `configs/factory.toml` is back in §6. Its claim that the file is outside the merge allowlist is true: `allowed_paths` at `4296edc` is `factory/**`, `docs/**`, `tests/test_factory/**` and `.factory/**`. Both Supersedes entries now name tickets. #165 is "[F-1] bands.yaml and the self-filing intent", which fits stage 10's new `intent.md`. §5 spells out `factory/loop.py`, and §13 X1 says "directly or transitively". |

The mechanical checks were re-run at `0dde478`:
- `grep -ni engine docs/factory/design.md` returns nothing;
- `grep -rni foreman docs/factory/` returns nothing;
- the changed files since `4296edc` are exactly criterion 16's set, plus `.factory/214/review.md`;
- the working tree is clean apart from this file.

## New in this cycle

### A. §12's new item cites a probe no source records (minor)

The restored item reads: "A probe in the re-check showed it does from a plain
directory." I found no record of that probe:
- the re-check, as `spec.md` records it verbatim, says nothing about `-I`;
- the source's own §12 says "I did not run it";
- `review.html` uses `python -I -B` for its own throwaway probes and proposes
  `python -I -m factory` as M3's fix, but reports no run of the hook that way.

It may have been relayed in-session, as the re-check was. As written, though,
it is a verification claim with no artifact behind it, inside the section whose
job is to say what was not verified.

**Fix.** Either cite where the probe is recorded, or drop that sentence and
keep "#216's tests prove it".

## Still open, all non-blocking

1. §9 `accept`, exit 1, says "the base diff is outside the radius". §7 now
   says the accept check also covers the hard-stop list. These do not
   contradict: at accept, the hard-stop paths in the radius are exactly the
   ones being approved. Adding "or touches the hard-stop list" would make the
   §9 cell match §7 and #222.
2. §13's legend says a *changed* row "says how". M8 and m6 do not. The
   source's M8 note: "the accepted radius comes from `plan.md`, so
   `split.toml` is not needed". The source's m6 note: "`run` never exits on
   its own, so nothing has to restart it". Restoring them would fix both.
3. §5's `blob(commit, path)` against #139's `blob(repo, commit, relpath)`.
   This was a nit in cycle 1, not taken.
4. `CONTEXT.md` Factory loop: "the same on-disk state". The loop's snapshot
   also holds launcher and PR state (#159). "The same snapshot" is the
   accurate phrase. This was a nit in cycle 1, not taken.

A last note, not a finding. §6 says `configs/factory.toml` is "written by the
maintainer", but #218 has the Builder add it. "Created by #218, owned by the
maintainer" would avoid the reading that #218 must not touch it.

## Suite

`python -m pytest -q -p no:cacheprovider` from the worktree root, at
`0dde478`, gave `1197 passed, 3 skipped, 25 deselected in 57.00s`. That is 0
failed, 0 errors and 0 xfailed. Criterion 17 is **met**.

## Could not verify

These carry over from cycle 1:
- that the re-check text in `spec.md` is verbatim;
- the source's §2 SVG, which I read as extracted text;
- whether the Supersedes notes list every superseded section.

New in this cycle: whether the §12 probe (finding A) happened. GitHub state,
including #218's amended body, is as read on 2026-10-22.
