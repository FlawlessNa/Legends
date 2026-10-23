---
ticket: 218
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "document holds until plan.md's docs_cleared is a list, not null, on the current proof, with factory doc check added to the row by #186"
---

# Spec review: routing v2, roles.py and the model table

**Verdict: `changes-requested`.** I read `spec.md` and `intent.md` at `aadfbf8`
against:

- issue #218 and the issues that consume it (#163, #222, #186, #145, #159);
- `design.md` §0, §2, §5, §6 and §8, plus `artifacts.md`, `roles.md` and `stages.md`;
- #219's spec;
- `routing.py`, `models.py`, `chain.py`, `cli.py`, `configs/factory-models.toml`, and the routing, models and cli tests.

The ticket is sound in its shape: two tables chosen by `Chain.version`, a pure
`ROWS_V2` over gathered facts, and v1 left alone. Seven findings block it,
because a builder could not settle the criteria without inventing the contract:

- a row whose condition names no fact (2);
- two rows that contradict each other once the Documenter commits (1);
- a model key that cannot load (3);
- an escalation that reads the wrong attempt (4);
- caps with no comparison (5);
- an equality test that has no "before" and goes red whenever any chain changes (6);
- test edits the spec does not name (7).

The rest are scope and contract gaps that the consumers (#163, #222, #159)
would otherwise each settle differently.

## What holds

- **"The commit that last wrote `proof.md`" is well defined.** It is
  `git -C <worktree> log -1 --format=%H -- .factory/<n>/proof.md`, taken from HEAD.
  - A merge of `dev` that leaves `proof.md` alone keeps the same answer. That is
    right, because criterion 6 then makes the proof stale on the merged source.
  - An uncommitted `proof.md` is invisible to it. That is also right, because the
    loop commits the proof.
  - Pin two things: the full 40-hex id, and the loop's git flags (finding 13).
- **The loop-stamped fields are constructible in tests without a writer.**
  `ROWS_V2` is pure over `ChainFacts`, and `spec-review.md` `commit`,
  `plan.commit` and `review.md` `commit` are front matter that a test writes. A
  test needs no loop for them. It does need their exact key names (finding 11)
  and #219's `TicketState`. `factory/state.py` is not on this branch yet, so the
  build waits for #219.
- **Criteria 8, 9 and 10 are decidable** from `state.submitted`, `state.accepted`,
  `chain.radius`, `radius_errors` and `chain.blob(root, "HEAD", ".factory/<n>/spec.md")`.
  Each reads a field #219 now contracts.
- **The override type change does not disturb `_check_escalation`.** That check
  reads only `override.use` against the weakest `by_stage` tier. The table's
  floor stays `standard`, so `use = "complex"` passes.

## 1. The Documenter's commit breaks both proof currency and review staleness

**Evidence.**
- Criterion 7 orders `build-implementing` before `document`.
- Criterion 6 holds `build-implementing` while any path outside `.factory/` differs between `proof.commit` and HEAD.
- #159 step 5 dispatches the Documenter *after* Prove, "judged and committed like a Builder turn", and only then takes the Reviewer's snapshot.
- #186 has the Documenter write `docs/**`, every `AGENTS.md` and `CONTEXT.md`.

So the first Documenter turn that edits a document makes the proof stale.
`ROWS_V2` then sends the ticket back to `build-implementing`, and the loop
dispatches a Builder with nothing to do.

Criterion 13 has the same root:
- The review is current when its stamp is "the commit that last wrote `proof.md`".
- Design §6 equates that stamp with the snapshot the Reviewer judged ("a snapshot at `proof.md`'s own commit").
- With a Documenter turn between them, the snapshot that includes the docs is a *later* commit.
- If the loop stamps the snapshot's commit, no review is ever current, and the loop never reaches `integrate`.
- If it stamps the proof's commit, the snapshot is not the thing stamped.

Design §6's staleness rule was written for R9's "no Document stage" and does
not survive the reversal unchanged.

**Fix.** State the contract this ticket's rows assume, and test it:

- The loop proves after every Documenter turn that passes judgement, as after a
  Builder turn (an obligation on #159 and #145). The proof then covers the docs,
  and criterion 6 holds after documenting.
- `review.md`'s `commit` is defined as the commit that last wrote `proof.md` *at
  the moment the Reviewer's snapshot is taken*. The snapshot is HEAD at that
  moment.
- Extend criterion 14's walk with a Documenter turn that edits one document:
  proof, then document, then re-proof, then review, then pass, then integrate.
- Put the obligation under "Not in scope", with #159 and #145 as owners.

## 2. Criterion 12's "on the current proof" names no fact

**Evidence.**
- `ChainFacts` holds `state`, the spec blob, source-differs and the last proof writer.
- Nothing in it, and nothing in #219's state, ties `docs_cleared` to a proof.
- `plan.md` is written by the Planner and then the Builder (design §6), and either can write `docs_cleared: []`.

As written, the row cannot be decided:
- After a `changes-requested` round, `docs_cleared` is still the list from the last round. The `document` stage is skipped for the new change.
- A Planner who fills `docs_cleared` skips the stage on the first round too.
- A list with mapping items is unread (`front_matter_lists`, `- path: x`), so that row holds forever.

The test "one red test per row" therefore has no pass condition for this row.

**Fix.** Give the row a stamped fact, in the pattern the other judged stages use:
- **The stamp.** After the Documenter's turn and its re-proof (finding 1), the
  loop writes a field into `plan.md`, such as `docs.commit`. Its value is the
  commit that last wrote `proof.md`.
- **The row.** `document` holds until that stamp equals the current last proof
  writer, and `docs_cleared` is a readable list.
- **What follows.** A Builder turn makes a new proof, so `document` runs again.
- **The format.** Pin the shape of a `docs_cleared` item: a scalar `path: reason`
  is read, while `- path: x` makes the whole list unread.
- **Ownership.** Say that `docs_cleared` is the Documenter's field, and that #163
  can enforce this only at file level.

## 3. `orchestrator = "standard"` cannot load, and `accept` gets a model nobody runs

**Evidence.**
- Criterion 18 maps `orchestrator` to `standard` in the model table.
- `_stages_of` (models.py:162-175) raises `TableError` for any `[by_stage]` key that is not a `Stage`.
- Criterion 16 adds only `spec-review` and `accept` to `Stage`.
- Criterion 17 gives each role a "model stage key", but the orchestrator has no stage.

There is also a second problem. `accept` becomes a `Stage`, and `NO_AGENT` is
`integrate` alone. So `factory model --stage accept` would answer `sonnet` by
default, for a stage that only the maintainer acts in.

**Fix.**
- Decide where a role-only key lives: a `[by_role]` block, or a model key that is
  not a `Stage`. Then say what `factory model` accepts for it.
- Make `accept` answer "no model", as `integrate` does.
- Name the shipped-table test this changes (finding 7).

## 4. The escalation reads an attempt that is not the one being dispatched

**Evidence.**
- #219 criterion 4: `attempt` counts dispatches of `state.stage`, and resets when the stage changes.
- #219's decision: `attempt_at_least = 2` "means the second dispatch". That reading holds only if the dispatch record is written *before* the model is resolved.
- #159 writes that record "before starting the worker", but nothing orders it against choosing the `WorkerSpec`'s model.

Criterion 18 says only that the fact is "an integer fact read from the ticket's
state". That leaves three failures open:
- **Off by one.** If the model is resolved first, the second dispatch reads `attempt = 1`, and the escalation never fires under a cap of 2.
- **A stale stage.** After a stage changes, `state.attempt` still belongs to the old stage. For example, a spec-review passed on its second attempt would escalate the Planner's first.
- **`--stage X` with a ticket** reads another stage's attempt.

**Fix.**
- Define the fact as "the attempt of the dispatch being resolved". It is
  `state.attempt` when `state.stage` equals the stage being resolved, and 1
  otherwise.
- State the ordering obligation on #159: the dispatch record first, then the model.
- Add tests:
  - `state.stage` differs from the resolved stage, with attempt 2: no escalation;
  - the `--stage` path;
  - v1 with no state.
- Validation:
  - Reject a `bool` for `attempt_at_least`. `isinstance(True, int)` is true, so an
    int check alone accepts `true`.
  - Reject a value below 2, because 1 matches every dispatch, as the empty `when`
    already rejected does.
  - Keep "predicates" in the `method_live` message, because
    `test_an_override_comparing_a_fact_to_a_non_boolean_is_a_table_error` matches
    that word.

## 5. Criterion 15's caps have no comparison and no position

**Evidence.** "Reaching configs/factory.toml's attempts or cycles cap blocks
naming the cap" leaves four things open:

- **The comparison.** `>=` or `>`?
- **Which stage it applies to.** `attempt` is the attempt of `state.stage`, which may be a stage already left (finding 4).
- **A worker still running.** #219 has a `worker` field. Design §8 lets the Builder run `next`, so a Builder on its second attempt that runs `factory next` would read "blocked: attempts cap" about itself and exit 3.
- **When a cycle counts.** It could count at `changes-requested`, or at the resubmission. Under `cycles = 2` that is the difference between the second rejection parking the ticket and a third round running.

Where the park and cap rows sit relative to the stage rows is not stated either,
yet criterion 7 says "first match wins". A pass at `cycles = 2` blocks or not
depending on that order.

**Fix.**
- Write each cap as a predicate over #219's fields. For example: the attempts
  cap blocks when `state.worker` is null, `state.stage` equals the stage the
  stage rows give, and `state.attempt >= attempts`.
- Say which verdict and count make the cycles cap block.
- Place the park and cap rows as guards before the stage rows, and test their
  order.
- Say whether `state.parked` is read, or only `park.md`.

## 6. The v1 equality test has no "before", and would go red on every future ticket

**Evidence.**
- Criterion 1 compares answers "before and after" over "every chain committed under .factory/", but the old code is gone once the change lands.
- The live `.factory/` changes all the time:
  - this ticket's own chain gains `plan.md` and a review during the build;
  - #219's chain moves on;
  - every later ticket adds a chain.
- A golden table of today's answers over the live directory therefore fails on the next commit to any chain. That would make the suite red for whoever touches one next.

The spec also lists this test under "Red tests". It cannot be red without the
change: it is a guard.

**Fix.**
- Freeze the inputs. Copy each chain, at the branch base, into a test fixture
  directory.
- Generate the expected answers once from the base's routing, and record in the
  plan the command used.
- Compare the whole `Next`, every field, plus the exception raised, if any.
- Include:
  - #202's `pass-with-notes` (named in the issue's acceptance);
  - a `chain: 1` fixture.
- Relabel it a non-regression guard.

## 7. Existing tests this spec changes, unnamed

**Evidence.**
- `tests/test_factory/test_cli.py::test_model_names_the_rule_that_fired` copies the real table and asserts that `qa` resolves to `sonnet # tier=standard`. Criterion 18 moves `qa` to `complex`, so the test goes red. The spec exempts only `test_routing.py` and `test_models.py`.
- `test_the_shipped_table_resolves_every_stage_to_something` asserts a model for every `Stage` except `integrate`. It changes if `accept` answers no model (finding 3).
- `test_the_shipped_table_routes_judgement_to_the_strong_tier` may gain `spec-review`.
- The "table's key list" exemption is deferred to the plan.

Under `AGENTS.md`, an edited test is behaviour that moved. The spec is where that
is named, not the plan.

There is also a v1 consequence the intent does not state. Moving `qa` to
`complex` changes the model for v1 live tickets at QA. That is fine, but the v1
constraint covers stage routing only, and the spec should say so.

**Fix.** List each test that changes and the behaviour that moved, in the spec.

## 8. The `document` row contradicts `design.md`, which says it wins on the target

**Evidence.** `design.md` still says:
- R9 "No Document stage" (line 36);
- §2 "Gone from today's stages: … `document` (R9)" (line 78), with no `document` in the diagram or table;
- §5 `models.py` "loses … `document`" (line 137);
- §8 has no documenter;
- §11 lists "Document stage" as not built (line 297).

Its preamble says that where it and the other docs disagree about the target,
"this document wins".

#186's body claims the `design.md` amendment, but #186 is P9 and outside §10's
build order, so this ticket lands a code row that the governing document denies,
for an unknown time. The Supersedes notes are wrong too:
- `stages.md`: "8 · Document: removed (ruling R9), #218";
- `roles.md`: "The Clerk, the Documenter and the Integrator go".

The spec cites the reversal only in "Source" and changes none of these.

**Fix.** This ticket makes the Document row true, so it should amend `design.md`:
- R9 (reversed, citing #186);
- §2's diagram, table and "Gone from" line;
- §5's `routing.py` and `models.py` rows;
- §6's `review.md` stamp, per finding 1;
- §8's role table, with the documenter.

It should also correct both Supersedes notes, and say in the PR that #186's
`design.md` bullet shrinks to the doc map. The alternative is a criterion that
states the contradiction outright. Silence is the one option `AGENTS.md` rules
out.

## 9. `roles.py`'s fields do not carry what #163, #222 and #159 read

**Evidence and fixes, by consumer.**

**Write scope (#163).**
- **The grammar.** The radius grammar is files and `dir/**`. It cannot express
  the Documenter's "every `AGENTS.md`", or #186's "`docs/**` except `docs/adr/**`".
  The issue said "globs, with `<n>`". The spec changed this to the radius grammar
  without saying how those two scopes are written. Decide: enumerate today's
  `AGENTS.md` files, add an exclusion form, or let the scope grammar differ from
  the radius grammar.
- **The two scopes disagree.** The issue's Documenter scope is `docs/**`, and
  #186's excludes `docs/adr/**`. Pick one.
- **The Builder's scope is dynamic.** It is `plan.md`'s radius within
  `acceptance.radius`, plus tests and `.factory/<n>/plan.md` (design §8). Say what
  `scope("builder", n)` returns. #163 must refuse `review.md`, `proof.md` and
  `acceptance.md` from it.

**Commands (#222).**
- Every worker's hooks run `python -m factory hook …` under its `FACTORY_ROLE`.
  If #222 enforces `allowed` on every command and `hook` is in no role's list,
  every hook call from a worker is refused.
- Name what is always allowed: `hook`, and probably `version`.
- Say how two-word commands are identified (`spec submit`, `plan check`,
  `doc check`, `merge check`).
- Give the Documenter's commands. §8 has none, because it has no Documenter.

**Where a role runs and which roles exist (#159).**
- The orchestrator runs in the primary checkout (§8). That is none of
  `own-worktree`, `snapshot` and `worktree`.
- `role_for` must answer for `accept`, `qa` and `integrate`, which no role acts
  in, and for the v1-only stages. Say whether it returns `None` or raises.

**`roles.md`.** Replacing its opening table with the v2 table removes the v1
roles that every hand-worked ticket still uses. State the v2 table beside the
v1 one, as criterion 20 does for `stages.md`, and pin the table's markdown shape
so the equality test has one parse.

## 10. `configs/factory.toml`: which checkout, which error, which keys

**Evidence.**
- **Which checkout.** `routing.resolve(repo_root, branch)` receives the ticket
  worktree. Read from there, a ticket branch could raise its own caps. That is
  the hole `_model` closes by reading the session's table ("a ticket branch must
  not be able to change its own model routing", cli.py:189).
- **Which error.** "A `TableError`-like misuse" contradicts `TableError`, which
  models.py documents as `NEEDS_HUMAN`, "not `MISUSE`". Criterion 19's "a clear
  error" names no exit code.
- **Which keys.** `wip` is a dispatch limit, not something routing reads. Design
  §6 has #218 create the file with `launcher`, `worker_timeout_min` and `poll_s`
  as well. The spec does not say whether unknown keys are an error. If they are,
  #159 and #220 must reopen the loader.
- **v1 must not read it.** Otherwise a missing file breaks v1 routing, against
  criterion 1.

**Fix.**
- Read it from the session's checkout, as the model table is read.
- Use exit 3, as for `TableError`.
- List the required keys and their types: positive integers.
- Say whether unknown keys are allowed.
- Make the read v2-only.
- Gather the caps into `ChainFacts`, so the rows stay pure.

## 11. Field names, SHA format and `artifacts.md` are not pinned

**Evidence.**
- **`plan.commit`.** In `chain.front_matter` this spelling is a nested `plan:`
  block with `commit:` under it. Design may only mean "`plan.md`'s `commit`", a
  top-level key. A test author and #159's writer will pick differently.
- **SHA format.** Nothing says the stamps are full SHAs. An abbreviated stamp
  never equals `state.submitted`.
- **`artifacts.md`.**
  - Its Supersedes note assigns "Verdicts: gains the factory loop's stamped
    `commit`, #218" to this ticket, but no criterion and no intent bullet touch
    it.
  - Its `spec-review.md` table lists `pass | changes-requested` only.
  - Its `docs_cleared` text still describes stage 8 after review.

**Fix.** Add a criterion that updates `artifacts.md` with:
- the exact keys and types for the `spec-review.md` and `review.md` `commit`, the
  `plan.md` stamp, and the documenter stamp from finding 2;
- the `docs_cleared` item format;
- a rule that stamps are full ids, compared as strings.

These are the writers' contracts for #159 and #222.

## 12. Unspecified v2 cases

These need decisions in the criteria.

- **`spec-review.md: fail`.** `VERDICTS` has it, and criterion 8 does not route it. Block, as `review` does?
- **A stale `changes-requested`.** Routing back to `design` or the Builder must apply only when the verdict is current. A stale one goes to its judge. The walk in 14 implies this, but criteria 8 and 13 do not say it.
- **`method: assent` at QA.** Is it skipped, as `suite` is?
- **What `Next` carries for v2.** `role`, `section` and `do` are what `factory next` prints and #159 reads. They should be `roles.py` names and the v2 `stages.md` sections.
- **Design and accept as "awaiting you".** Design §9 says `next` exits 3 for "blocked, parked, or awaiting you". If they are marked `blocked_by`, `_model` returns `NEEDS_HUMAN` (cli.py:217), and the Designer can never be given a model (#222 starts it with one). Decide how waiting on a person is represented without that.

## 13. Gathering facts: holding on a missing fact, git's flags, exceptions in the CLI

**Evidence and fixes.**
- **A missing fact.** "A missing fact … makes its row hold" routes the ticket
  *to* that stage. The loop then dispatches a worker that cannot fix a git
  failure, and spends attempts. Block instead, naming the fact.
- **Git's flags.** Design §4.7 says every loop git call runs with
  `-c core.hooksPath=<empty> -c core.fsmonitor=false`. `gather` runs inside the
  loop, and `chain.blob` passes neither flag. Require them in `gather`.
- **Exceptions in the CLI.** `state.load` can raise `StateError`, and
  `UnknownChainVersion` "propagates as misuse". `_next` and `_model` catch only
  `MalformedVerdict`, so both would print a traceback. `cli.py` is not among the
  intent's affected systems, but the Shape changes `factory model <n>`. Name
  `cli.py`, and give each exception's exit code (`UnknownChainVersion` → 2,
  `StateError` → 3). Check #219's `park`, which records stage null when routing
  raises.

## 14. Scope: a split is safer, though not required

The issue says "one table, so one ticket", and the criteria can be fixed
without splitting. But the halves differ in readiness:

- **`roles.py`, the model table and `factory.toml` (findings 3, 4, 9 and 10).**
  These settle what #163, #222, #143 and #152 are blocked on.
- **`ROWS_V2` (findings 1, 2, 5, 6 and 12).** This carries every open contract
  with #159, #145 and #186.

The `Stage` enum would go with the first half, since the model table needs it.
Splitting would unblock four P1 tickets while the routing contract with the loop
is settled. If it stays one ticket, the plan should order the work so that the
roles and models half is green first. This is the maintainer's call. It does not
count toward the verdict.
