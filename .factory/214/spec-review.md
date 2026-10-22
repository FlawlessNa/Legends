---
ticket: 214
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-22
criterion_quoted: "every re-check finding X1 to X8 and a to i is folded into the section it changes, and section 13 maps each to where it now lives"
---

# Spec review: commit the agreed factory design

**Verdict: `changes-requested`.** The spec is aimed at the right outcome. Its
"what folded in means" rule is the right rule, and the naming decision is
right. But four problems would let a Builder satisfy every criterion and still
ship a wrong document, or would stop the Builder from satisfying them at all:

- the re-check findings that criterion 2 depends on exist in no file;
- two criteria contradict each other over one line of `artifacts.md`;
- two folds contradict the design, and the spec does not decide them;
- one re-check finding contradicts the GitHub graph that criterion 4 says to copy.

None of these needs the intent reopened. All of them are edits to `spec.md`,
plus one question for the maintainer (finding 4).

I read `intent.md`, `spec.md`, issue #214, epic #171, the bodies and blocked-by
links of every roadmap ticket (#215 to #224, #207, #139, #163, #145, #143,
#152, #159), the closed #211, both `.lavish/` sources as text, `CONTEXT.md`,
`docs/agents/engine-architecture.md`, `docs/agents/domain.md`,
`docs/factory/README.md` and `artifacts.md`, and the code the source cites, at
`4296edc`. Every claim below was checked by reading. I ran no tests.

## Blocking

### 1. The re-check is in no file, so criterion 2 cannot be built or checked

The spec's Source says the re-check was "relayed in the session that produced
the roadmap". It is not in `.lavish/`, in the spec or in any issue. Fragments
appear in ticket bodies: X7 in #207, a and d in #139, X3 in #220 and #145, X4
and f in #221, X2 and X6 in #222, and c in #145. X1 and X8 do not appear by
name anywhere. h appears only in #159, and only by implication.

So a Builder in a fresh worktree has nothing to fold. A reviewer reading the
diff has nothing to check §13 against. Criterion 2 is the one this ticket
exists for, and as written it can only be checked from memory.

**Fix.** Put the re-check into `spec.md`, verbatim: X1 to X8 and a to i, as
relayed. Then add a fold table: for each finding, every section it changes.
That table is the checkable form of "folded into the section it changes". The
singular "section" in the criterion is also wrong, because most findings touch
several sections. A starting table, from my reading of the source against the
findings (the specifier should verify it):

| Finding | Source text it changes |
| --- | --- |
| X1 | §10 order; §5 `routing.py` row (v1 chains keep v1 routing); §5 `chain.py` row |
| X2 | §2 design row, §4 rule 4 and §8 `designer` row, which all say "ticket worktree"; §6 `acceptance.md` (blob recorded in `state.json`); dispatch refusal on a dirty worktree (§4 or §9) |
| X3 | §5 `proof.py` ("runs the suite at HEAD", implicitly in the ticket worktree); §4 rule 2 (stop the worker first); §8 `stop` |
| X4 | §4 rule 2 ("plus ignored files under `.claude/`"); §7 last row ("differs from base"); §13 M3 row |
| X5 | §9 `accept` and `OpenPR`; §7 radius row |
| X6 | §4 rule 2; §5 `gitops.py`; §5 `state.py` (`turn_base` is not trusted back from disk); §6 `acceptance.md` (`base_sha`) |
| X7 | §5 `hooks.py` ("judges the session's own worktree only"); §10 S3; **§13 B3 row** (finding 3) |
| X8 | §5 `proof.py`; §6 `proof.md` (`red` gains `error`, per #145) |
| a | §5 `chain.py` ("recognises a v1 chain (no acceptance.md)"); §6 `intent.md` |
| b | §6 `plan.md` |
| c | §2 review row; **§6 `review.md` staleness** (finding 3) |
| d | §6 `plan.md` radius; §9 `plan check` |
| e | §5 `models.py` row ("loses plan and document") |
| f | §4 rule 2; §5 `gitops.py` |
| g | §3 row 2 ("Seven of eight"). Verified: 9 `spec-review.md` files at `4296edc`, 8 `changes-requested`, #202 `pass-with-notes` |
| h | §9 `run`; §10 S1 |
| i | §7 last row; §9 or §11 |

### 2. Criteria 8 and 9 cannot both hold

Criterion 8 says "Foreman appears nowhere in docs/factory/". Criterion 9 says
that in `artifacts.md`, apart from the Supersedes note, "nothing else in them
changes". But `docs/factory/artifacts.md:143` reads "when the Foreman (#159)
starts recording it". `grep -rni foreman docs/factory/` finds that one line.
The issue has the same tension ("replace it in `docs/factory/`" against "no
other content in those four documents changes"), and the spec inherited it
without resolving it.

Two related traps the spec should name:

- `design.md` and the Supersedes notes cannot mention Foreman either, not even
  to retire it. Under criterion 8, the history lives only in `CONTEXT.md`.
- Foreman survives outside `docs/factory/`, in `factory/models.py:5`, `:41` and
  `configs/factory-models.toml:2`, `:20`, `:44`. Criterion 11 correctly keeps
  these out of the radius, but "Foreman is retired" (intent) then reads as more
  than this ticket does. Say so under Not in scope, and name the owner. #218
  (S5) rewrites the models table.

**Fix.** Criterion 9 becomes: "... and nothing else in them changes, except
that `artifacts.md:143`'s 'the Foreman (#159)' becomes 'the factory loop
(#159)'."

### 3. Two folds contradict the design, and the spec must decide them

"The design must not contradict itself" is a good rule, but two findings break
sentences in a way a port cannot repair.

- **c and §6 `review.md`.** The source says a review "is stale when it differs
  from `proof.commit`, which is what ends the loop in d1". Under c, the
  Reviewer's snapshot is at **`proof.md`'s commit**. #145 confirms that
  `proof.md` is committed by the loop "with its own commit", after the commit it
  proves. So the engine-stamped `review.commit` never equals `proof.commit`:
  every review is stale, and d1's endless review loop comes back.

  **Fix.** The spec decides the rule. The obvious one is B2's rule, which #145
  already uses for proofs: a review is current when no source differs between
  `review.commit` and `proof.commit`, ignoring `.factory/`.
- **X7 and §13 B3.** The B3 row reads "changed: ... The session-written log is
  not needed". X7 restores the log (#207: `<git-common-dir>/factory/sessions/
  <session_id>`).

  **Fix.** The row becomes "taken", and points at S3. §13 is a ledger that
  findings fold into, not only a map of where they went.

### 4. X1 contradicts GitHub's blocked-by graph for P6

X1 says P4, P5 and P6 depend on S4 and S5. On GitHub, #145 (P6) is blocked by
#139 and #221 only. #221 is blocked by #207, which leads back to #217, #216 and
#214. Nothing reaches #218 (S5), even transitively. P4 and P5 do reach both
(#222 through #218; #163 directly).

Criterion 4 ("the blocked-by order that GitHub holds") and criterion 2 (X1
folded in) therefore require two different §10s. #145 also reads
`acceptance.base_sha`, which #222 (P4) writes, and #145 is not blocked by
#222. That may be deliberate, since a test can fake acceptance, but it is
worth checking at the same time.

**Fix.** Ask the maintainer, before build, whether to add the #145 → #218
link. Either way, have §10 list each row's blockers explicitly, dated
2026-10-22, so the diff can be checked against `gh issue view` rather than
against a graph that moves.

## Major

### 5. The ticket bodies already go past the source and cite `design.md` for it

The roadmap tickets were rewritten on 2026-10-22 and cite `design.md §n`. In
places they are more specific than the source plus the re-check, and some
contradict the source:

- #215 asks **five** launcher questions, and cites §8 and §12. The source's §8
  and §12 say **four**. The fifth, the Bash TTY question, sits separately in §12.
- #145: `red: red|green|error|none`, `base_sha`, and "about 60 s at
  4296edc". Source §6 has `red|green|none`, and §12 says "I have not timed the
  suite".
- #221 and #159: `hooks_disabled`, `assert_untouched`, and a heartbeat showing
  whether the primary is dirty.

Some of these are elaborations of X findings. The five questions and the suite
timing are not. The spec states no precedence, so the Builder will port the
source and produce a `design.md` that the tickets citing it contradict.

**Fix.** Add a criterion: "Where a roadmap ticket cites `design.md §n`, that
section does not contradict the ticket body as of 2026-10-22." List the known
divergences above, and the rule for the rest. I suggest that the design states
the decision and the ticket owns the detail.

### 6. Citation anchors other than section numbers are lost in a markdown port

Criterion 1 protects `§n`, but the tickets cite finer anchors:

- #217 cites "§3 (d2, d5)". Source §5, §10 and §11 cite d1, d2, d5 and d6. In
  the HTML these are `<li id="d1">` to `id="d6"`, and they are **invisible in
  the rendered page**. A faithful port drops them.
- §4 rules are cited by number: #207 "rule 2", #219 "rule 5", #221 "rules 2-4".
  The source's `<ol>` keeps the numbers, but a port into `-` bullets would not.
- R1 to R11, S1 to S5, P1 to P8, L0, E1, E2, and B, M, m, X and a to i, are
  cited throughout.

**Fix.** Add a criterion: "the ids d1 to d6, R1 to R11, the step ids and the
finding ids appear as visible text, and §4 is a numbered list in the source's
order." Also, `[P1]` #219 sits in milestone "Factory **P0**", while milestone
"Factory **P1**: parts" holds P2 to P8. §10 should say which it means wherever
it writes "P1".

### 7. Nothing requires `design.md` to say it is not built yet

The source ends with "Nothing here is implemented". `AGENTS.md` and
`README.md` send every ticket agent to `docs/factory/`, and `README.md`'s whole
convention is marking what is real. That convention is what #211, absorbed
here, asked for. `design.md` describes commands, files and stages that do not
exist. The Supersedes notes protect the four old documents, but nothing
protects a reader of `design.md`.

**Fix.** Add a criterion: "`design.md` opens with its status: agreed
2026-10-22, read against `4296edc`, nothing in it built except what §3 says
holds today, and each part becomes true when its §10 ticket merges." The
`README.md` index entry should say the same in one line. `README.md`'s own
"## The stages" table is also superseded by §2 and gets no note. Decide whether
the index line is enough. I think it is.

### 8. Criterion 5 covers code, but the stale claims are not code

`4296edc` is still the merge base: `origin/movements-improvements` is at
`4296edc`. The code citations I spot-checked hold: `cli.py:98`, `:138`,
`:277`, `:438`; `hooks.py:140`, `:196`; `chain.py:122`, `:199`;
`routing.py:209-216`; `merge.py:72`; `merge-policy.md:40`;
`models.py:162-170`.

The stale claims are about the repository and GitHub:

- **d6:** "#140, #162, #206 and #209 are merged and open". All four are
  **CLOSED** now (`gh issue view`). The defect is still real, but its evidence
  is false.
- **g:** the spec-review count.
- §3 rows 5 and 6 (no protection, no rulesets, no permissions block). The epic
  asks the maintainer to change exactly these.

**Fix.** Extend criterion 5: "every statement about the repository or GitHub
state is true at `4296edc` or on 2026-10-22, and says which". Reword d6 to the
defect plus "closed by hand in the 2026-10-22 cleanup".

## Minor

### 9. §11 is not held to the roadmap

Only §10 must match #171. But the source's §11 cites #161 and #186, which are
both closed as absorbed. It omits #158, which #171 defers with QA. It does not
match the epic's Deferred list (merging by rule: #151, #160; documentation:
#181-#185, #187, #188; housekeeping: #136, #210).

**Fix.** Add a criterion: §11's issue numbers match #171's Deferred list.

### 10. Criterion 9's Supersedes note is not specified tightly enough to check

"Naming what `design.md` replaces" does not set a granularity, and it drops the
issue's second clause: the documents "describe *today's* behaviour until the
roadmap ticket owning each part lands". That clause is in the spec's intent
constraints but not in its criteria.

**Fix.** Each note sits immediately after the H1. It lists the superseded
sections by heading, each with the ticket number that will change it, and it
carries the "true of today until then" sentence. Note that live gate messages
cite `bootstrap.md` "rule 3" and `stages.md` "stage 2" (`hooks.py:124`, `:134`).
That is a concrete reason the notes must not renumber anything.

### 11. Criterion 6 is not checkable as worded, and misses identifiers

"Called the factory loop, never the engine" reads as prose. The source also
has the module `engine.py`, `engine.plan(snapshot)`, an "engine lock", "Engine
state", "Engine counters", and an "ENGINE (factory run)" lane in the §2
diagram. The spec's Naming section says the module is `factory/loop.py` (#159
cites "§5 (`loop.py`)"), but no criterion requires it.

**Fix.** "§5 names the module `factory/loop.py`, and `grep -ni engine
docs/factory/design.md` matches only lines about the bot's `Engine`."

### 12. Criterion 11 is too wide inside `docs/factory/`

Criterion 11 permits changes to `merge-policy.md`, which is a protected path
(`merge.py` `protected_paths`) and belongs to #217 by the spec's own Not in
scope. It also permits changes to `stage-template.md`, and to any part of
`README.md`.

**Fix.** Enumerate the files that may change: `design.md` (new), `README.md`
(index entry only), the four Supersedes targets, `CONTEXT.md`, and
`.factory/214/`.

Separately, the spec gives the wrong test as its reason for keeping the suite
green. The test that reads a file this ticket touches is
`test_the_factory_readme_links_the_policy` (`test_merge.py:675`). It asserts
`(merge-policy.md)` in `README.md`, so the index edit must keep that link.
"The suite stays green" should be a criterion too, since it is the only
mechanical check an assent ticket has.

### 13. The §2 diagram has no stated port

The lifecycle is an inline SVG with three lanes, and it is where "you are out
from here" lives. Say what replaces it: a text diagram, or nothing, because the
stage table carries the content.

## The naming decision: right, with two refinements

Verified. `CONTEXT.md:10` defines a Session as "spawning the `Engine`", and
`CONTEXT.md:3` calls `botting/` "the generic engine". `engine-architecture.md`
is titled "Engine architecture", names the "Engine Process", and maps it to
`botting/core/engine.py`. A `factory/engine.py` would be a second `engine.py`
in the repo, naming a different thing. Renaming is right. The roadmap tickets
already say "the loop", and none of the bodies I scanned says "engine". "The
factory loop" and `factory/loop.py` are good choices.

Two refinements belong in criterion 7.

**(a) Say where the entry goes, and add the Orchestrator.**

`CONTEXT.md` has no factory section, and `docs/agents/domain.md` calls this a
single-context repo. Add a `## The factory` section rather than slotting the
entry under `## Language`.

#211, which this ticket absorbs, used **Foreman to mean the Orchestrator**
("Orchestrator, not Foreman"). #162's chain and `models.py` used it to mean the
program. The design separates the two: §9's Orchestrator is the agent you talk
to, and the loop is the program. A `CONTEXT.md` that defines only the loop and
rejects Foreman leaves the reader of #211 with the wrong mapping.

**Fix.** Add an **Orchestrator** entry beside the loop's. Each `_Avoid_` line
should give its reason in the house style, for example "_Avoid_: engine — that
is the bot's `Engine` (`botting/core/engine.py`)". #183's planned vocabulary
lint will need that reason to be context-aware.

**(b) The spec's principle proves more than it applies.**

"A factory word must not collide with a `CONTEXT.md` term" also catches other
words the design uses:

- **snapshot**: `CONTEXT.md:216` already lists it under `_Avoid_`, as "a copy
  of bot data".
- **Attempt** and **Session**: both are defined terms with other meanings
  (`CONTEXT.md:284`, `:9`).
- **loop**: the bot's route cycle, its "decision-loop interval", and the
  Engine's "hot loop" (`engine-architecture.md:39`).

I would not rename these. Engine is the only one that is also a module and
class name. But the section's preamble should scope the factory senses of
session, attempt, snapshot and run. The entry should be "factory loop", with
bare "the loop" acceptable inside `docs/factory/` only.

## The criteria, one by one

| # | Criterion | Judgement |
| --- | --- | --- |
| 1 | numbering 0-13 | Sound but too narrow: finer anchors are lost (6) |
| 2 | X1-X8, a-i folded; §13 maps them | **Uncheckable**: no source text (1). "The section" should be "every section". Two folds need decisions (3) |
| 3 | §0 rulings decided, R1 amended | Sound. The source's R1 already carries the amendment, so this is a faithful port plus "decided" |
| 4 | §10 as ticketed, GitHub's order | Conflicts with X1 for P6 (4). Checkable only if §10 lists the blockers |
| 5 | code claims true at `4296edc` | Sound for code. Misses repository and GitHub state, where the stale claims are (8) |
| 6 | factory loop, never the engine | Right decision. Make it a grep, and cover identifiers (11) |
| 7 | `CONTEXT.md` entry | Right. Say where it goes, add the Orchestrator, give reasons (naming) |
| 8 | no Foreman in `docs/factory/` | **Contradicts 9** (2) |
| 9 | Supersedes notes; nothing else changes | Contradicts 8. Granularity unspecified, and the "true of today" clause is dropped (10) |
| 10 | `README.md` links `design.md` | Sound. Name the list ("## The rest") and the status line (7) |
| 11 | no file outside ... changes | Too wide inside `docs/factory/` (12) |
| — | missing | Status line (7); ticket-body agreement (5); §11 against #171 (9); suite green (12) |

## What this review could not verify

- The re-check's exact wording. I worked from the summary relayed to me, which
  is the same gap finding 1 describes.
- Whether the source HTML I read is the final accepted version. Its R1 already
  carries the amendment, which suggests it is, but nothing records the
  version.
- Whether the X1 edge for P6 is a missing GitHub link or an overstatement in
  X1. Only the maintainer can say.
- The fold table in finding 1 comes from my own reading. It is a starting
  point, not a verified mapping.
