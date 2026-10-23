---
ticket: 219
stage: design
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "the state holds version, ticket, stage, attempt, cycles (a mapping from judged stage to a count), worker (name, role, started_at, or null), turn_base, submitted, parked (kind and reason, or null), designer_session and an append-only log of entries each with at, event and detail"
---

# Spec review: the factory loop's state outside the worktrees, and factory park

**Verdict: `changes-requested`.** I read `spec.md` at `1cf2121` against the
intent, issue #219, `design.md` §4 (rule 5), §6, §8 and §9, `factory/AGENTS.md`,
and the code on this branch. I also read the three consumers: #218, #159 and
#222.

The shape is right: one JSON file under the common dir, atomic replace, and a
`park` that writes only `park.md`. Three findings block:

- The field list leaves out a record that the design and #222 put in
  `state.json` (finding 1).
- On Windows, `os.replace` fails whenever a reader holds the file open. I
  measured this (finding 2).
- The no-locking argument ignores #222's writers, which run outside
  `factory run` (finding 3).

The other findings are gaps in decidability. Each one has a fix that takes a
sentence.

Probes ran with `python -I -B` (3.14) in my scratchpad, on this machine
(Windows 11, NTFS).

## 1. The acceptance record is missing from the field list (blocking)

The weakest criterion is quoted in the front matter. It lists eleven fields,
and none of them holds acceptance.

**Evidence.**

- Design §4 rule 5: "The accepted spec blob and the base SHA are recorded there
  [in `state.json`] at acceptance, so a hand-written `acceptance.md` accepts
  nothing."
- Design §2, accept row: the loop "records the accepted blob in its own state".
- #222, `factory accept`: "**Also records the accepted `spec_blob` in
  `state.json`.**"
- #222, `spec submit`: it is "Refused after acceptance". The cheapest
  trustworthy test for that is this same record.
- #218, accept row: `acceptance.md` must match "the loop's acceptance record in
  `state.json`".

Three consumers read a field that this ticket does not define. Criterion 3
then makes the gap expensive. It rejects any `version` other than 1, and says
nothing about missing or unknown keys. So #222 either adds the field silently,
which leaves the loader's behaviour on an extra key undefined, or bumps the
version to 2 the week after it ships.

The other fields cover what the consumers read:

- `submitted` (#218 design row, #222 `spec submit`);
- `turn_base` and `worker` (#159 Dispatch);
- `cycles` (R4, #218 caps);
- `attempt` (#218 `attempt_at_least`; see finding 7 for its semantics);
- `parked` and `designer_session`.

**Fix.**

- Add `accepted`, either null or an object with at least `spec_blob` and
  `base_sha`. I would add `commit`, the commit that wrote `acceptance.md`, and
  `accepted_at` as well, so #218 can match the record field for field.
- Extend criterion 3: a missing field, a field of the wrong type, or a `ticket`
  that differs from the directory raises `StateError` naming the file.
- State what an unknown key does. I suggest `StateError` too, so that every
  schema change goes through `version`, which is why the version is there
  (Decisions, point 2).

## 2. `os.replace` on Windows fails while anyone reads `state.json` (blocking)

Criterion 4 makes the replace the whole protection, and the Shape says "Atomic
replace is what protects a reader". On Windows, the reader is the problem.

**Evidence.**

- One process opened `state.json` with plain `open()` and held it. `os.replace`
  onto it raised `PermissionError: [WinError 5] Access is denied`.
- A reader in a second process holding the file open gave the same error.
- A tight-loop reader in one process ran against 3000 replaces from another:

  | Side | Result |
  | --- | --- |
  | Writer | **2897 of 3000 replaces raised `PermissionError`**. 103 succeeded. |
  | Reader | 6226 clean reads, **107 `PermissionError`**, 0 partial, 0 missing |

So atomicity holds: no reader ever saw a torn or absent file. But both sides
fail transiently. Python's `open` does not request `FILE_SHARE_DELETE`, so any
open handle blocks the rename. The handle can come from `factory status`
(#159), an editor, the indexer or antivirus.

The read side hides a worse hazard. Criterion 3 says a missing file gives a
fresh state. Suppose `load` catches `OSError` rather than `FileNotFoundError`.
Then a transient `PermissionError` reads as "no state", and the next `save`
writes a fresh state over the real one. The loop silently forgets the ticket's
counters, its submission and its acceptance.

**Fix.** Add to criterion 4, or as a new criterion:

- `save` retries `os.replace` on `PermissionError` for a bounded time. On
  exhaustion it raises `StateError` naming the file, and the previous
  `state.json` is untouched.
- `load` returns a fresh state only on `FileNotFoundError`. Any other `OSError`
  is retried, then raised as `StateError`. **It never gives a fresh state.**
- Tests, all offline:
  - `os.replace` patched to raise `PermissionError` twice and then succeed: the
    save lands.
  - `os.replace` patched to raise `PermissionError` every time: `StateError`,
    and the old state still loads.
  - The read patched to raise `PermissionError`: `StateError`, not a fresh
    state. This one is red against an `except OSError` loader.

## 3. "No locking" holds only if the loop is the only writer, and it is not (blocking)

The Shape reads: "No locking: one `factory run` at a time is #159's OS lock."
That lock serialises loops. It does not serialise the loop against these
writers:

- `factory feature new`, which "Writes `state.json` (P1)" (#222 step 3);
- `factory spec submit`, which "records `state.submitted`" (#222);
- `factory accept`, which "records the accepted `spec_blob` in `state.json`"
  (#222).

Each is a separate process, started by the maintainer or the Designer while
`factory run` ticks. Atomic replace stops torn reads. It does not stop lost
updates. Take an accept, a load followed by a save, interleaved with a loop
tick doing the same. One of the two writes is lost. If the lost one is the
acceptance record, the ticket waits at accept forever. If it is a cycle count,
a cap is silently missed.

The spec also never says whether `factory park` writes `state.json`. The intent
says it leaves "a `park.md` the loop and routing can read", which suggests not,
but `parked` is a state field.

**Fix.** Decide, and put the decision in a criterion. Either:

- **(a)** `state.py` exposes `update(repo_root, ticket, fn)`, which does load →
  `fn` → save under an exclusive lock file in the ticket's state directory.
  Callers use `update`, not `load` then `save`. Test: with the lock held,
  `update` waits, then times out with `StateError`. Or
- **(b)** a single-writer rule: only the loop writes `state.json`, and #222's
  commands ask the loop to write. That moves work into #222 and #159, and the
  spec must name it in "Not in scope".

Either way, add: `factory park` does not write `state.json`. The loop mirrors
`park.md` into `parked` (#159).

## 4. `park`'s stage is undefined when routing blocks or raises

Criterion 11 reads: "the stage recorded in park.md is the stage routing gives
the ticket at that moment."

**Evidence.**

- `routing.resolve` returns `stage=None` on three rows: the inconsistent-chain
  guard, `review.md` fail, and `qa.md` fail (routing.py:159-163, 226-235).
- It raises `MalformedVerdict` on a verdict outside `VERDICTS` (routing.py:88-104).
- `_next` and `_model` turn that exception into exit 3.

These are exactly the moments a worker would park: a chain it cannot proceed
on. As written, the criterion gives no answer. An implementation could crash,
refuse to park, or write `stage: None`.

**Fix.** Add a criterion:

- When routing returns no stage, or raises `MalformedVerdict`, `park` still
  writes `park.md`, with `stage: null`, and exits 0.
- One test for a blocked chain and one for a malformed verdict.

Also say that the branch passed to `resolve` for `park <n>` is `issue/<n>-`, as
`_next` does. Then the stage comes from the ticket's worktree, not the session's.

## 5. Exit 1 for a second park contradicts the contract and design §9

Criterion 10: "exits 1 without writing when park.md already exists, naming the
kind already recorded."

**Evidence.**

- `factory/AGENTS.md`: 1 means "The gate failed — Fix it and re-run. Never
  proceed". 3 means "Needs a human — Stop, comment on the ticket, hand back".
  It also says: "Never return 1 for something a person has to settle."
- An already-parked ticket is, by definition, waiting for a person. A worker
  told "fix it and re-run" has one obvious fix, deleting `park.md`, and that is
  the one act the spec says belongs to the maintainer or the loop.
- Design §9's `park` row has `—` under 1 and under 3. The spec adds an exit
  code the design does not have, and does not say so.

**Fix.**

- Exit 3 for an existing `park.md`, still without writing, naming the recorded
  kind.
- List every exit code `park` can give:
  - 2 for neither or both flags. argparse already does this; name it so the
    test asserts it.
  - 2 for an empty `--reason ""` or `--question ""`.
  - 2 for `<n>` with no worktree, and 3 for several worktrees. Both come from
    `_ticket_root`, and neither is in the criteria today.
- Say that the spec amends design §9's `park` row, and update that row in the
  same PR.

## 6. Which ticket, and which worktree, `park` writes to

Criterion 9: "park resolves the ticket from <n> through worktree_for, or from
the session's own branch when <n> is omitted, and writes in that ticket's
worktree."

**a. The omitted form is ambiguous.** It can be read as "the session's own
worktree" (what `_next` does: cli.py:146-154 uses `session` directly) or as
`worktree_for(ticket_from_branch(...))`. The two differ once a second worktree
sits on `issue/<n>-*`.

**b. That second worktree is coming.** #222 puts the Designer in
`issue/<n>-<slug>-design`. I checked: `ticket_from_branch("issue/219-loop-state-design")`
returns `219`. So after #222:

- `park <n>` (and `next <n>`) sees two worktrees and exits 3.
- A Designer running `park` with no `<n>` writes `park.md` into its own
  worktree. Routing and the loop read the ticket worktree, so they never see it.
  The loop copies back `intent.md`, `spec.md` and `answers.md` only (§4 rule 4).

**c. Three of the five roles that §8 says "may run `park`" run on a detached
snapshot:** spec-reviewer, planner and reviewer. `current_branch` returns None
on a detached HEAD, so plain `park` exits 2 under criterion 10. `park <n>` from
a snapshot writes into the ticket worktree, which is exactly what §4 rule 3's
`assert_untouched` exists to flag.

**Fix.**

- Make criterion 9 say "the session's own worktree root" for the omitted form.
- Add to "Not in scope" that parking from a snapshot, and from the Designer's
  worktree, belongs to #159 and #222. The likely answer is copy-back of
  `park.md`, or a resolution through `FACTORY_TICKET`. Say that `park <n>` from
  a snapshot is not the supported path. This ticket does not have to solve it,
  but it must not leave a criterion that reads as if it had.

## 7. The fresh state, and what `attempt` counts

Criterion 3 says a missing file "returns a fresh state for that ticket" and
never says what that state holds. #218's model rule is
`when = { attempt_at_least = 2 }`, glossed as "A stage's second attempt runs on
the complex tier". R4 allows 2 attempts per stage.

Two readings fit the spec:

- `attempt` is the 1-based number of the current attempt;
- `attempt` counts the failures so far.

They differ by one at exactly the threshold #218 tests. Whether `attempt` is
per stage (reset when `stage` changes) or per ticket is also unstated.

**Fix.**

- Pin the fresh state:
  - `version: 1`, `ticket: <n>`;
  - `stage: null`, `attempt: <0 or 1>`, `cycles: {}`;
  - `worker`, `turn_base`, `submitted`, `parked`, `designer_session` and
    `accepted` all null;
  - `log: []`.
- Define `attempt` in one sentence: "the number of the current stage's attempt,
  starting at 1", or the other reading. Resetting it is the loop's job.
- Optionally, name the domain of `parked.kind`. The loop parks for reasons
  `park.md` does not have: a cap, a fingerprint change, a `.claude/**` radius
  (#159).

## 8. The interrupted-write test needs to prove what it claims

The red test reads: "an interrupted write, simulated by raising inside
`os.replace` after the temp file is written, leaving the old state readable."

It does catch a naive `write_text` straight to `state.json`, provided it
asserts that `save` raised. Such an implementation never calls `os.replace`,
so it neither raises nor leaves the old state. But it does not show the "after
the temp file is written" half. An implementation that raises before writing
anything passes too.

**Fix.** The fake `os.replace` asserts three things before it raises:

- its source exists;
- it sits in the same directory as `state.json`, which is what makes the rename
  atomic on one volume;
- it holds the new state.

Patch it where `state.py` looks it up (`factory.state.os.replace`, or `os.replace`
if the module calls `os.replace`), not a `from os import replace` alias.

For the stale-temp test, leave a `state.json.tmp-<pid>` holding a **valid,
different** state, and assert `load` returns `state.json`'s contents.

Separately, "survives a crash" in the intent holds for a process crash. It does
not hold for power loss without `fsync` of the temp file before the replace.
Either add the `fsync` and list power loss under *Could not verify*, or narrow
the wording to process crashes.

## 9. `render_run_md` determinism, and the shape of `cycles` in front matter

Criterion 7: "returns the same text for the same state".

Two `TicketState`s whose `cycles` dicts hold the same entries in a different
insertion order are equal, but a naive render prints them differently. The
criterion is then false for "the same state", read as `==`.

A frozen dataclass holding a `dict` and a `list` is also neither hashable nor
actually frozen. Criterion 6's "never rewrites" is easier to hold with a tuple.

The repo's own parser (`chain.front_matter`) reads scalars and one level of
nesting, flattened to dotted keys. The criterion should say how `cycles`
appears.

**Fix.**

- Render `cycles` sorted by key, as `cycles.<stage>: <n>`, so `front_matter`
  reads it back.
- Make the test build the two states with opposite insertion orders.
- Store `log` as a tuple and `cycles` as a read-only mapping.
- Add `run.md`'s front-matter fields to `artifacts.md` beside `park.md`'s.

## 10. This branch does not contain #139, and criterion 12 depends on it

Criterion 12 reads: "read_chain(...).park returns the written front matter, and
docs/factory/artifacts.md's park.md contract lists ticket, kind, stage and
parked_at."

**Evidence.**

- The merge base with `origin/dev` is `016692b`, which is before #139's merge
  at `4d98b50` (`git merge-base --is-ancestor 4d98b50 HEAD` fails).
- On this branch, `factory/chain.py` has no `LOOP_ARTIFACTS` and no
  `Chain.park`, and `artifacts.md` has no `park.md` section.
- On `origin/dev` all three exist (chain.py:47-51, 350, 455; artifacts.md:178-192).
  There, the `park.md` contract already lists `kind` and `stage`.

The spec names only #207 as its base. As things stand, criterion 12 cannot be
met without rebasing onto dev, and the artifacts change is an amendment to an
existing section, not an addition.

**Fix.**

- Name #139 in the Source section as a base requirement, and have the plan
  rebase onto `dev` once #235 merges, or onto `dev` with #207 on top.
- Reword criterion 12's second half as "amends `park.md` (v2) to add `ticket`
  and `parked_at`".

## 11. Smaller decidability gaps

- **Criterion 13**, "nothing in this ticket writes into a ticket worktree except
  park.md", is a claim about the whole diff, so nothing checks it today. Make
  it a test: from a linked worktree, run `load`, `save`, `with_log`, `save`
  again and `render_run_md`, then assert that
  `git status --porcelain --ignored` is unchanged in every worktree. Keep "the
  full suite is green" as its own criterion.
- **Outside a repository**, `common_dir` returns None. Say that `load` and
  `save` raise `StateError` there.
- **The state directory** is `<common>/factory/<n>/`, beside #207's
  `<common>/factory/sessions/`. They do not collide. Whatever enumerates
  tickets' state (#159 `status`, #210) must take only numeric names. One line
  in `state.py`'s docstring would save #159 from finding this out.

## What I checked and found sound

- `chain.common_dir` gives the same directory for the primary checkout and
  every linked worktree. A per-ticket file under it is what criterion 1 needs.
- #218 reads `submitted`, the cycle counters and `attempt`, and #159 reads
  `worker`, `turn_base`, `parked` and the log. All are present, apart from the
  semantics in finding 7.
- Not committing `park.md` matches design §4 rule 4 and the issue.
- Deferring the role allowlist to #218's `roles.py` loses nothing, since every
  role may park (§8).
