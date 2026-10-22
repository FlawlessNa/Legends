---
ticket: 214
stage: design
method: assent
criteria:
  - docs/factory/design.md exists and keeps the source's section numbering, 0 to 13, so tickets citing design.md §n resolve
  - the ids d1 to d6, R1 to R11, the step ids (D1, L0, S1 to S5, P1 to P8, E1, E2, DONE) and the finding ids (B, M, m, X, a to i) appear as visible text, and §4 is a numbered list in the source's order
  - design.md opens with its status, saying agreed 2026-10-22, read against 4296edc, nothing built except what §3 says holds today, each part true when its §10 ticket merges
  - every re-check finding X1 to X8 and a to i changes every section the fold table in this spec names, and §13 maps each finding to where it now lives
  - the folds this spec decides are applied as decided, so a review is current only when its stamped commit is the commit that wrote the current proof.md, §13's B3 row reads taken and its X1 row reads changed, and §4 gains a seventh rule
  - section 0 records all eleven rulings as decided on 2026-10-22, with R1 as amended (the maintainer reads the spec, never the plan)
  - section 10 lists every roadmap ticket with its issue number and its blockers as GitHub holds them on 2026-10-22, dated
  - section 11's issue numbers match #171's Deferred list
  - every statement about code is true at 4296edc, citing a file and line or a named function, and every statement about repository or GitHub state says whether it holds at 4296edc or on 2026-10-22
  - where a roadmap ticket cites design.md §n, that section does not contradict the ticket body as of 2026-10-22, with the design stating the decision and the ticket owning the detail
  - §5 names the module factory/loop.py, and grep -ni engine docs/factory/design.md matches only lines about the bot's Engine
  - CONTEXT.md gains a section headed The factory, with entries for Factory loop and Orchestrator, each _Avoid_ line giving its reason, and a preamble scoping the factory senses of session, attempt, snapshot and run
  - Foreman appears nowhere in docs/factory/
  - stages.md, roles.md, artifacts.md and bootstrap.md each carry a Supersedes note immediately after the H1 that lists superseded sections by heading with their owning ticket and says the page stays true of today until then, and nothing else in them changes except artifacts.md's "the Foreman (#159)", which becomes "the factory loop (#159)"
  - README.md's "## The rest" list gains one entry linking design.md with a one-line status, and keeps its link to merge-policy.md
  - the only files changed are docs/factory/design.md (new), docs/factory/README.md, the four Supersedes targets, CONTEXT.md and .factory/214/
  - pytest from the worktree root reports 0 failed, 0 errors, 0 xfailed
specified_by: claude
specified_at: 2026-10-22
revised_at: 2026-10-22
revised_after: spec-review-2.md (changes-requested, 4 findings)
---

# Spec: commit the agreed factory design

## Source

- Issue #214.
- The agreed design: `.lavish/factory-design.html` in the maintainer's checkout. This is the final version: its R1 carries the amendment of 2026-10-22, and nothing changed after acceptance.
- The **re-check**: the second independent review, recorded verbatim below, because it exists in no other file (review finding 1).

## The re-check, as delivered on 2026-10-22

Verdict: **ready after named fixes**.

- **X1 (blocker), §10 sequencing.** Phase 1 could not start "once S3 lands".
  - P4 needs `blob()` (S4), the role allowlist (S5) and the submission recorded in `state.json` (P1).
  - P5 needs `roles.py` (S5) and list parsing (S4).
  - P6 needs the `proof.md` schema (S4).
  - S5 settles "the caps" and "the verdict for the current submission", but both are `state.json` facts, which arrive in P1.
  - Once S5 merges, routing v2 drops `plan` and `document` and routes to `accept`. That breaks every Phase 1 ticket worked by hand.

  Fix: order the tickets S1–S3, then P1 and P2, then S4, then S5 (reading a state snapshot), then P3–P6. S5 keeps v1 routing for v1 chains until E2.
- **X2, the Designer is an unjudged writer in the ticket worktree.** It is never dispatched, so the loop never judges it, and "one writer at a time" is not a mechanism. A shell-written `acceptance.md` matching the spec blob would start a build without the maintainer. Its uncommitted files would fail a Builder's turn, and the reset would destroy its drafts. Fix:
  - run the Designer in its own worktree, and have the loop copy its files in by pathspec;
  - `accept` records the accepted blob in `state.json`, and `acceptance.md` is valid only when it matches;
  - refuse to dispatch into a dirty worktree.
- **X3, "finished" is idle, not stopped.** A worker idle while a background task runs can resume and write during the proof or a judge's run. The proof also runs Builder code in the ticket worktree after the turn is judged. Fix:
  - stop the worker before judging (the Designer excepted);
  - run both proof runs in throwaway worktrees;
  - re-verify HEAD and `status --ignored` after the proof and after each judge turn.
- **X4, the `.claude` check fires on Claude Code's own writes.** "Don't ask again" writes `.claude/settings.local.json`, which would park every ticket. Fix: parse the files and refuse only `env.FACTORY_HOOKS`, `disableAllHooks` and `hooks`.
- **X5, B1 was only half taken.** Radius and hard-stop checks on `base...HEAD` were dropped, so commits made outside a judged turn are never checked. Fix: check `base...HEAD` against the radius and the hard-stop list at accept and at OpenPR, failing closed.
- **X6, nothing judges writes outside the worktree.** That covers:
  - the primary checkout's `factory/` (which, after S1, is the judge);
  - `~/.claude/settings*.json`;
  - `state.json`'s `turn_base`;
  - the base ref;
  - `<common>/config` and `hooks/`, which run code inside the credentialed loop.

  Fix:
  - fingerprint all of those before and after each turn;
  - keep `turn_base` in memory, and require it to be an ancestor of HEAD;
  - record the base SHA at accept;
  - run loop git with `core.hooksPath` empty and `core.fsmonitor=false`.
- **X7, S3 silently reverted #206.** Judging only the session's own worktree loses #206's guarantee for off-ticket sessions, and there is no loop yet to cover it. Fix: keep a per-session target log for sessions with no role.
- **X8, "red" is not well defined.** A collection error, a mistyped nodeid, a marker-deselected test, or `conftest.py`/`pytest.ini` restored to base all exit non-zero. Fix:
  - require exit 1 with the nodeid among the junitxml failures, and record anything else as `error`;
  - the test side is `tests/**`, `conftest.py` and `pytest.ini`;
  - handle added and deleted files;
  - use the base SHA from accept;
  - define `none` for test-only work and refactors.
- **Minors:**
  - **a.** "v1 = no `acceptance.md`" matches every v2 chain before accept; use `chain: 2`.
  - **b.** `plan.md` is not bound to the submission; stamp `plan.commit`.
  - **c.** The Reviewer's snapshot at `proof.commit` cannot contain `proof.md`; snapshot at `proof.md`'s own commit.
  - **d.** Glob-against-glob overlap is undecidable with merge.py's matcher; restrict the radius to files and `dir/**`.
  - **e.** `test` in the models table must go with the enum.
  - **f.** The loop's commit runs the installed pre-commit; run pre-commit as part of judgement, then commit with hooks off.
  - **g.** 8 of 9 committed spec-reviews say `changes-requested`, not 7 of 8.
  - **h.** A long-lived `run` keeps stale code; the heartbeat prints the primary's HEAD and whether it is dirty, and `run` re-execs when that HEAD changes.
  - **i.** A ticket whose radius includes `.claude/**` can never be loop-worked; it parks for a person.

## The fold table

"Folded in" means the sentence a finding corrects is changed wherever it appears. Nothing is appended as a later section that overrides an earlier one. Each finding changes every section listed:

| Finding | Sections it changes |
| --- | --- |
| X1 | §5 `routing.py` (two tables; v1 kept), §5 `chain.py`, §10, §13 (changed) |
| X2 | §2 design row, §4 rules 4 and 5, §6 `acceptance.md`, §8 designer row, §9 `accept` |
| X3 | §4 rules 2 and 3, §5 `proof.py`, §6 `proof.md` (the red test runs in a throwaway worktree), §8 `stop` |
| X4 | §4 rule 2, §7 last row, §13 M3 |
| X5 | §7 radius row, §9 `accept` and OpenPR, §13 B1 |
| X6 | §4 rules 2, 5 and 7, §5 `gitops.py` and `state.py`, §6 `acceptance.md` |
| X7 | §5 `hooks.py`, §10 #207, §13 B3 |
| X8 | §5 `proof.py`, §6 `plan.md` (`red_test`, `none`) and `proof.md` (`red`) |
| a | §5 `chain.py`, §6 `intent.md` |
| b | §2 build-planning row, §6 `plan.md` |
| c | §2 review row, §6 `review.md`, §8 reviewer row |
| d | §5 `chain.py`, §6 `plan.md`, §9 `plan check`, §13 m1 |
| e | §5 `models.py` |
| f | §4 rules 2 and 7 |
| g | §3 |
| h | §7 last row, §8, §9 `run` |
| i | §7 last row |

## Decided here (review finding 3)

- **Review staleness.** With c, the Reviewer judges a snapshot at `proof.md`'s own commit. **A review is current when its loop-stamped `commit` is the commit that wrote the current `proof.md`**, which is the snapshot it judged. The loop proves after *every* Builder turn, so any Builder turn makes the review stale. That includes a turn that changed only `plan.md`, where three of the Reviewer's duties live: the red test, `docs_cleared` and *Could not verify*. A rule that compared source alone would have kept a `changes-requested` review "current" after a `plan.md`-only fix, and recreated d1 (spec-review-2 finding 1).
- **§10 follows GitHub, not X1's linear order.** Every dependency X1 names is in the graph. Its linear order is dropped on purpose: #139 may start before #216, and #221 before #218. §13's X1 row reads "changed".
- **§4 gains a seventh rule**, appended after the six in the source: the loop's git never runs code a worker could have written (`core.hooksPath` empty, `core.fsmonitor=false`, pre-commit run as part of judgement). X6 and f fold into it.
- **§13 B3 reads "taken".** X7 restored the per-session target log that the "changed" row had dropped.
- **No #145 → #218 link (review finding 4).** P6 needs the `proof.md` schema (#139) and the adapters (#221), and GitHub has both links. X1's own text says "P6 needs the proof.md schema (S4)". It needs nothing from routing. P6 reads `acceptance.base_sha`, and its tests fake an acceptance rather than waiting for #222. The two documents do not contradict each other.

## Precedence with the ticket bodies (review finding 5)

The roadmap tickets were written alongside this design, and in places they are more specific. **The design states the decision; the ticket owns the detail.** `design.md` must not contradict a ticket citing it. Known cases, which the design adopts:

- #215 asks five launcher questions, not four (the fifth is the terminal question, R8).
- #145 adds `red: error` and `base_sha`, and times the suite at about 60 s at `4296edc` (measured 2026-10-22: 1170 passed in 58 s).
- #221 and #159 name `hooks_disabled`, `assert_untouched` and the dirty-primary heartbeat.

## Naming

`CONTEXT.md` defines a Session as spawning the `Engine`, and `engine-architecture.md` maps that to `botting/core/engine.py`. So the factory's program is **the factory loop**, its command `factory run`, its module `factory/loop.py`. Bare "the loop" is acceptable inside `docs/factory/` only.

`CONTEXT.md` gets a new `## The factory` section. It holds **Factory loop** (`_Avoid_`: Foreman, retired; engine, the bot's `Engine`; orchestrator, the conversational agent) and **Orchestrator** (`_Avoid_`: Foreman, which #211 used for this; engine). A preamble says that inside the factory, session, attempt, snapshot and run carry their factory meanings, distinct from the bot's Session and Attempt.

## Verification method: assent

The proof is a diff a reader can check against the source, the re-check above, the code at `4296edc`, and GitHub on 2026-10-22. No test is added, because no behaviour changes. The suite must stay green: `test_the_factory_readme_links_the_policy` (`test_merge.py:675`) reads the `README.md` this ticket edits.

The §2 lifecycle diagram (an SVG) is ported as a text diagram, followed by the stage table.

## Not in scope

- Rewriting the four superseded documents. Each roadmap ticket updates the part it changes. The notes must not renumber anything, because live gate messages cite `bootstrap.md` rule 3 and `stages.md` stage 2 (`hooks.py:124`, `:134`).
- "Foreman" in `factory/models.py` and `configs/factory-models.toml`. #218 rewrites the models table.
- `merge-policy.md` and `stage-template.md`. Their errors belong to #217.
- `.lavish/`, which stays gitignored history.
