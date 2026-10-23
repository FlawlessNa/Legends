---
ticket: 219
stage: design
cycle: 2
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "attempt counts the dispatches of the current stage, starting at 1 on that stage's first dispatch and resetting when the stage changes, and cycles maps each judged stage to the rounds it has used"
---

# Spec review, cycle 2: the factory loop's state outside the worktrees, and factory park

**Verdict: `pass`.** I checked only the eleven findings from `spec-review.md`,
against `spec.md` at `04f7a50`, which has `origin/dev` merged in at `2196fca`.
All eleven are resolved in the criteria.

Four notes remain, a to d below. None of them changes what a criterion
requires, so the plan can settle each one, and must. I re-ran three probes
with `python -I -B` on this machine, against the new numbers the spec commits
to.

## 1. The acceptance record: resolved

Criterion 2 now lists `accepted`, with `spec_blob`, `base_sha`, `accepted_by`
and `accepted_at`, or null. Every field is required. "A missing, unknown or
mistyped field" raises `StateError`. That is what #218's accept row and #222's
`accept` need. `commit` was optional in my fix, and its absence is fine:
#218 matches the blob.

The phrase "naming the file and the field" cannot hold for malformed JSON or a
bad version, because there is no field to name. Read it as "naming the field
where there is one".

## 2. `PermissionError` on Windows: resolved, and the numbers hold

Criterion 6 covers both sides. "load never treats a PermissionError as a missing
file", and criterion 3 confines the fresh state to "only when state.json does not
exist".

I tested the Shape's bound of 50 × 20 ms against the same tight-loop reader that
made 2897 of 3000 bare replaces fail. **The bounded retry gave up 0 times in
200 saves. It needed at most 13 tries, and 2.9 on average.** The bound is
generous for any real reader.

## 3. Lost updates: resolved, with notes a and b

Criterion 7 adds `update`, under an OS lock on `state.lock` that the OS releases
if the process dies. The Shape names the writers this guards against:
`factory run` and #222's three commands. Criterion 11 says `park` "never writes
state.json".

I tested the Windows half. One process held `msvcrt.locking(fd, LK_NBLCK, 1)` on
an empty `state.lock`. A second process was refused (errno 13). After the
holder was killed, the second acquired the lock at once. Locking past the end
of an empty file works.

**Note a: `save` stays public, so criterion 7 binds only callers of `update`.**
#222 could write `load` → change → `save` and lose updates exactly as before.
The plan should do one of two things:

- make the direct write private, keeping `save` for a fresh file only; or
- have `save`'s docstring say that every writer of an existing state goes
  through `update`. Then #222's reviewer has a sentence to check against.

**Note b: the concurrent test must be red without the lock, reliably.** "Two
processes update concurrently and both changes survive" can pass by luck when
the lock is stashed, because the race window is tiny. Make `change` wait inside
the critical section: sleep, or wait on a marker file the other process writes.
Then the unlocked run loses an update every time.

Also name the lock wait's bound. `fcntl.flock` blocks forever, and
`msvcrt.LK_LOCK` gives up after about 10 s. Exhausting that bound should raise
`StateError`, matching criterion 6.

## 4. `park`'s stage: resolved

Criterion 12: null "when routing gives none or raises, and park still exits 0".
The red tests name a blocked chain and a malformed verdict.

## 5. Exit codes: resolved

Criterion 13 gives:

- 3 for an existing `park.md`, without writing, naming the kind;
- 2 for flag misuse, an empty text, or no ticket;
- whatever `_ticket_root` gives, 2 or 3, "as factory next does".

It also makes the amendment to design §9's `park` row part of the work. The
Decisions section explains why 3 and not 1. That is the contract's reading.

## 6. Ticket and worktree resolution: resolved

Criterion 11 now says "the session's own worktree" when `<n>` is omitted. The
snapshot case and the Designer's branch name are now under "Not in scope", with
#159 and #222 as owners. Each entry says what breaks, so neither can be
mistaken for solved.

**Note c.** Something must mirror `park.md` into `state.parked`, now that `park`
never writes state. That is #159's `snapshot()`. One line under "Not in scope"
would name it.

## 7. The fresh state and `attempt`: resolved, with note d

Criterion 3 pins the fresh state exactly: `attempt 0`, `cycles` empty, `log`
empty, and every other field null. Criterion 4 defines `attempt` as 1-based per
stage, reset on a stage change. The Decisions section ties that to #218:
`attempt_at_least = 2` means the second dispatch.

**Note d: criterion 4 is the weakest criterion,** quoted above. It defines
meaning, but nothing in this ticket dispatches. No function here increments or
resets `attempt`, and no red test names it. As written it is decidable only as
documentation. The plan should choose:

- **(i)** a small pure helper, such as `dispatched(state, stage) -> TicketState`,
  that sets or resets `attempt` and `stage`. Tests: a first dispatch gives 1, a
  second gives 2, a new stage gives 1.
- **(ii)** state that the criterion is met by `TicketState`'s docstring, and that
  #159 owes the behaviour and its test.

Option (i) is cheap. It also keeps #159 and #218's `factory model` from reading
the field two ways.

## 8. The interrupted-write test: resolved

The fake `os.replace` asserts that its source exists, sits in the same
directory and holds the new state, then raises. The stale temp file holds a
different valid state. Criterion 5 adds fsync and narrows the claim to "a
process killed".

The test raises an exception rather than killing the process. Both leave the
previous `state.json` untouched, so it is a fair stand-in, but the PR body
should say that "killed" was simulated.

One implementation detail: the read-only mapping (`types.MappingProxyType`)
compares equal regardless of insertion order, which I checked. `json.dumps`
refuses it, though, so `save` must convert it with `dict(...)`.

## 9. `render_run_md`: resolved

Criterion 9 now reads: "identical text for equal states whatever order cycles was
built in". It uses sorted `cycles.<stage>` keys, which `chain.front_matter`
flattens back. Criterion 8 makes `cycles` and `log` read-only. Criterion 14
adds `run.md`'s fields to `artifacts.md`.

## 10. #139 on the base: resolved

`2196fca` merges `origin/dev`. `LOOP_ARTIFACTS`, `Chain.park` and
`artifacts.md`'s `park.md (v2)` section are now present. Criterion 14 says
"adds ticket and parked_at" to that existing contract, which is the right verb.

## 11. Smaller gaps: resolved

- Criterion 15 is the `git status --porcelain --ignored` invariant, measured in
  every ticket worktree.
- Criterion 1 raises `StateError` outside a repository.
- The Decisions section records that listing tickets' state must take only
  numeric names under `<common>/factory/`, beside #207's `sessions/`.
