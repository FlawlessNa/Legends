---
ticket: 214
stage: review
verdict: changes-requested
reviewed_by: claude (reviewer subagent, separate session from builder and spec reviewer)
reviewed_at: 2026-10-22
commit: 1e42d7af56d81650888c3ae3c917db689c2fd20f
---

# Review: commit the agreed factory design

**Verdict: `changes-requested`.** The port is careful and mostly faithful. Every
code citation holds at `4296edc`, §10 matches GitHub exactly, and §11 matches
#171. The decided folds (review staleness, B3 taken, X1 changed, rule 7) are
applied. But three re-check findings are not folded into every section the fold
table names. One of them, X4, leaves `design.md` contradicting itself between
§4 rule 2 and §7, and that is the main risk this ticket's spec names. The fixes
are sentence-level edits to `design.md`.

I read `spec.md`, the three spec reviews, `plan.md`, the full diff
`4296edc..1e42d7a`, the source `.lavish/factory-design.html` as extracted text,
the bodies and blocked-by links of #171, #214 to #224, #207, #139, #163, #145,
#143, #152 and #159, and the cited code at `4296edc`.

## Criteria

| # | Criterion | Judgement |
| --- | --- | --- |
| 1 | Numbering 0 to 13 | **Met.** Headings §0 to §13, in the source's order. |
| 2 | Ids visible; §4 numbered in source order | **Met.** d1–d6, R1–R11, D1, L0, S1–S5, P1–P8, E1, E2, DONE, B/M/m and X1–X8 all appear as text, and a to i are §13 rows. §4 is `1.` to `7.`, with the source's six first. |
| 3 | Status line | **Met.** Line 3 says all four things. |
| 4 | Every X and a–i finding changes every section the fold table names | **Not met.** X4 is not in §4 rule 2 (finding 1). X5 is not in §9 OpenPR, and its "hard-stop list" is folded nowhere (finding 2). X3's "re-verify after the proof" is missing (finding 3). Every other row checks out (see below). |
| 5 | Decided folds | **Met.** §2 review row and §6 `review.md` carry the identity rule, with spec-review-3's "proven turn" refinement. §13 B3 reads "taken", X1 reads "changed". §4 rule 7 states hooksPath, fsmonitor and pre-commit as judgement. |
| 6 | §0: eleven rulings, decided 2026-10-22, R1 amended | **Met.** |
| 7 | §10 blockers as GitHub holds them, dated | **Met.** All 18 rows match `dependencies/blocked_by` and the milestones, as checked on 2026-10-22. |
| 8 | §11 matches #171's Deferred list | **Met.** Its numbers are #154–#158, #167–#169, #151, #160, #164–#166, #170, #181–#185, #187, #188, #136 and #210. Each is open, in *Factory: after done*. |
| 9 | Code statements true at `4296edc`; repo and GitHub statements dated | **Met**, with one nit (finding 8, `.gitattributes`). Checked: `cli.py:98`, `:138`, `:277`, `:438`; `hooks.py:140`, `:196`; `chain.py:122`, `:199`; `routing.py:209–216`; `merge.py:72`; `merge-policy.md:40`; `models.py:162–170`; `VERDICTS`; the settings matcher; `factory-hook.sh`'s `-m`; and 8 of 9 `spec-review.md` files `changes-requested`, with #202's `pass-with-notes`. On GitHub: dev is the default branch, the workflow is absent from dev, there are 0 rulesets, `movements-improvements` is unprotected, and #140, #162, #206 and #209 were closed on 2026-10-22. |
| 10 | No citing ticket contradicted | **Not met (minor).** §5 `roles.py` contradicts #218's runs-in enum (finding 4). Every other citing ticket agrees. |
| 11 | `factory/loop.py`; `engine` grep | **Met.** `grep -ni engine` returns nothing. §5 says `loop.py` in a table of `factory/` modules. `factory/loop.py` is spelled out only in `CONTEXT.md` (nit, finding 8). |
| 12 | `CONTEXT.md` `## The factory` | **Met in content.** It differs from the house style (finding 7). |
| 13 | No Foreman in `docs/factory/` | **Met.** `grep -rni foreman docs/factory/` returns nothing. |
| 14 | Supersedes notes; nothing else changes | **Met.** Each note sits right after the H1, nothing is renumbered, and the only other change is `artifacts.md`'s Foreman line. Two entries name no ticket (nit, finding 8). |
| 15 | `README.md` entry; `merge-policy.md` link kept | **Met.** |
| 16 | Changed-file set | **Met.** The changed files are `design.md` (new), `README.md`, `stages.md`, `roles.md`, `artifacts.md`, `bootstrap.md`, `CONTEXT.md` and `.factory/214/*`. The working tree is clean. |
| 17 | pytest green | **Met.** 1197 passed, 3 skipped, 25 deselected; 0 failed, 0 errors, 0 xfailed. |

### Criterion 4, row by row

- **X1.** Met: §5 `routing.py` (two tables), §5 `chain.py` (`chain: 2`), §10 and §13 "changed".
- **X2.** Met: the §2 design row, §4 rule 4 (own worktree, dirty-worktree refusal), rule 5, §6 `acceptance.md` ("valid only when it matches the loop's record"), the §8 designer row and §9 `accept`.
- **X3.** Partly met: §4 rule 2 (stop first), rule 3, §5 `proof.py`, §6 (throwaway worktree) and §8 `stop`. The post-proof re-check is missing (finding 3).
- **X4.** Not met: §7's last row and §13 M3 are changed, but §4 rule 2 is not (finding 1).
- **X5.** Not met: §7 and §13 B1 are changed, but §9 OpenPR is not, and the hard-stop list is folded nowhere (finding 2).
- **X6.** Met: §4 rules 2, 5 and 7, §5 `gitops.py` and `state.py`, and §6 `acceptance.md` `base_sha`.
- **X7.** Met: §5 `hooks.py`, §10 #207 and §13 B3.
- **X8.** Met: §5 `proof.py`, §6 `plan.md` (`none`, `kind`) and `proof.md` (`error`), plus the red-test procedure.
- **a to i.** All met, in every section named.

I found no surviving sentence from the source that contradicts a fold, except §4 rule 2 against X4. The removed sentences are all gone:
- "stale when it differs from `proof.commit`";
- "Designer, in the ticket worktree";
- "parallel once S3 lands";
- "decide_stop judges the session's own worktree only";
- "no acceptance.md";
- "Seven of eight";
- "differs from base".

## Findings

### 1. X4 is not folded into §4 rule 2, so §4 contradicts §7 (blocking)

§4 rule 2 takes a turn diff that includes "ignored files under `.claude/`", then
says "Run the same per-path rules the hooks run". Every turn in which Claude
Code wrote `.claude/settings.local.json` itself is then judged as a write to
`.claude/`. No worker's scope in §8 includes that path, so the turn fails.
That is exactly X4's failure, reached through §4 instead of §7. §7's last row
says the opposite: `hooks_disabled` parses the files, "so a byte comparison
would park everything". Rule 2's ordered list never mentions `hooks_disabled`.
#159's JudgeTurn does ("Check `hooks_disabled` and compare the fingerprint").

**Fix.** In §4 rule 2's order, add a step: check `hooks_disabled` (§7). Say
that `.claude/` entries in the turn diff are judged by it, not by the per-path
write rules.

### 2. X5 is not folded into §9 OpenPR, and its hard-stop half is lost (blocking)

- **§9 is unchanged.** The fold table lists "§9 `accept` and OpenPR". §9's
  OpenPR sentence still says only that it "exits 1 when *Could not verify* is
  empty". The base check at OpenPR appears only in §7.
- **The hard-stop half is lost.** X5's fix is to check `base...HEAD` "against
  the radius **and the hard-stop list**". The §7 radius row and §9 `accept`
  name only the radius. The source's §7 binding cell also said "plus hard-stop
  paths not in `hard_stop_approved`", and the port dropped that clause without
  trace. Both citing tickets state the hard-stop half: #222 "against the
  radius and the hard-stop list", and #159 "inside `acceptance.radius` and
  `hard_stop_approved`".

**Fix.**
- §7 radius row: "Plus `base_sha...HEAD` against the radius and
  `hard_stop_approved` at accept and at OpenPR, failing closed".
- §9 `accept`, exit 1: "...or the base diff is outside the radius or touches
  an unapproved hard-stop path".
- §9's OpenPR paragraph: add the base check, failing closed, before the
  *Could not verify* check.

### 3. X3's "re-verify after the proof" is missing

X3's third fix re-verifies HEAD and `status --ignored` "after the proof and
after each judge turn". §4 rule 3 asserts this only after a judge, and says
"status", not `status --ignored`. Nothing says it after a proof run, which
executes Builder-written code. #145 ("the ticket worktree's HEAD and status
are unchanged by a proof run") and #159 ("Prove. Then `assert_untouched`")
both have it.

**Fix.** In §5 `proof.py` (or §4 rule 3), say that `assert_untouched` runs
after every proof run as well as every judge turn. Make rule 3 say
`status --ignored`.

### 4. §5 `roles.py` contradicts #218's runs-in values (minor)

§5 gives runs-in as `worktree|snapshot|own-worktree`. #218, which cites §5,
gives `worktree|snapshot`. The design's value follows X2 and agrees with #222,
so #218 is the stale side. Under the spec's precedence rule ("the design
states the decision; the ticket owns the detail"), the design should not pin
an enum that the owning ticket spells differently.

**Fix.** Either §5 says "where it runs" without the literal enum, or the
coordinator amends #218. The second is a GitHub change, outside this ticket's
radius. In the same vein, as a nit:
- §5 writes `blob(commit, path)`, where #139 has `blob(repo, commit, relpath)`.

**For the coordinator, and not a defect here:** #218's accept row ("until
`acceptance.md` exists and its `spec_blob` equals the blob of `spec.md` at
HEAD") lacks X2's "matches the loop's record", which §2, §4 rule 5 and #222
all have.

### 5. §13 lost the source's "How" column and its legend (minor)

The source's §13 classified every finding as taken, changed, deferred, fixed
or "taken, extended". It also defined the terms: "'Changed' means the problem
is solved another way, and that way needs checking." The port keeps a label
only on B3 and X1. So "changed" is now undefined, and the reader §13 exists
for cannot see which rows need re-checking. M8's note is lost, for example:
"changed in one way: the accepted radius comes from `plan.md`, so `split.toml`
is not needed".

**Fix.** Restore the column, with the one-line legend, for both tables.

### 6. §12 dropped an item that is still unverified (minor)

The source's §12 said this was not run: "That `python -I -m factory` from a
worktree loads the primary checkout's code... I did not run it." Nothing has
run it since. #216 will prove it, but at `4296edc` it is unverified, and §7's
last row rests on it.

**Fix.** Restore the item, pointing at #216.

### 7. `CONTEXT.md`'s new section departs from the house style (minor)

Every entry above it writes `_Avoid_` on one line: `_Avoid_: Term, term —
reason.` The new entries use a bulleted list of `Term: reason`. No other
section opens with a bulleted preamble either. The planned vocabulary lint
(#183) will read `_Avoid_` lines, so one shape matters.

**Fix.** Use `_Avoid_: Foreman — the retired name; engine — the bot's
`Engine` (`botting/core/engine.py`); orchestrator — the agent the maintainer
talks to.` Write the preamble as a sentence. Separately, a nit: "the same
on-disk state always produces the same next action" is narrower than the
design. `snapshot()` also reads launcher and PR state (#159), so "the same
snapshot" is the accurate phrase.

### 8. Nits

- **§6 "Line endings."** "`.gitattributes` sets `.factory/** text eol=lf`" is
  present tense, and the file does not exist at `4296edc`. Add "(#217)".
- **`configs/factory.toml` was dropped.** The source's §6 row is gone
  (attempts, cycles, wip, `worker_timeout_min`, `poll_s`). #218 creates the
  file and #159 ticks on `poll_s`. §8's "or a timeout" now names no setting.
- **Supersedes notes.** `bootstrap.md`'s "each Phase 0 ticket" and
  `stages.md`'s "10 · Maintain: deferred" name no ticket. Each note is
  followed by two blank lines.
- **§5.** The table says `loop.py`. Writing `factory/loop.py` once, for
  example in the §5 lead-in ("modules under `factory/`"), would make
  criterion 11 literal.
- **§13 X1.** "Every dependency it names is a GitHub link." P4 → S4 is
  transitive, through #218, so "is in GitHub's graph" is accurate.

## Suite

`python -m pytest -q -p no:cacheprovider` from the worktree root, at
`1e42d7a`, gave `1197 passed, 3 skipped, 25 deselected in 53.66s`. That is 0
failed, 0 errors and 0 xfailed. The plan's figures agree. Criterion 17 is
**met**.

## Could not verify

- That the re-check text in `spec.md` is verbatim. No file holds the
  original, so I checked the folds against the spec's version.
- The source's §2 SVG. I read the HTML as extracted text, so I checked the
  text diagram against the lane labels and the stage table, not against the
  drawing.
- Whether the four Supersedes notes list *every* superseded section. Each
  listed heading exists and names a plausible owner. I did not audit each page
  section by section against the design.
- GitHub state is as read on 2026-10-22 during this review. Links and bodies
  can move after it.
