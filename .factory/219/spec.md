---
ticket: 219
stage: design
method: suite
criteria:
  - factory/state.py stores one ticket's state at <git-common-dir>/factory/<n>/state.json, where the common dir comes from chain.common_dir, and load or save outside any repository raises StateError
  - the state holds exactly version, ticket, stage, attempt, cycles, worker, turn_base, submitted, accepted, parked, designer_session and log, with accepted being spec_blob, base_sha, accepted_by and accepted_at or null, and a file with a missing, unknown or mistyped field, a version other than 1, or malformed JSON raises StateError naming the file and the field
  - a fresh state is version 1 for that ticket with stage, worker, turn_base, submitted, accepted, parked and designer_session null, attempt 0, cycles empty and log empty, and load returns it only when state.json does not exist
  - attempt counts the dispatches of the current stage, starting at 1 on that stage's first dispatch and resetting when the stage changes, and cycles maps each judged stage to the rounds it has used
  - save writes a temporary file in the same directory, flushes and fsyncs it, then replaces state.json with os.replace, so a process killed after the temporary file is written leaves the previous state readable, and a stale temporary file holding a different valid state never shadows state.json
  - save and load retry a PermissionError from a concurrent reader or writer a bounded number of times, then raise StateError, and load never treats a PermissionError as a missing file
  - update(repo_root, ticket, change) loads, applies change and saves while holding an OS lock on <common>/factory/<n>/state.lock that the OS releases if the process dies, so two processes updating at once lose neither update, proven with concurrent processes
  - a state saved and loaded again is equal to the original, the log only ever grows by appending, and cycles and log are read-only once constructed
  - render_run_md(state) returns identical text for equal states whatever order cycles was built in, with front matter holding ticket, stage, attempt and one cycles.<stage> key per judged stage in sorted order, and a body table of the log in order
  - factory park [<n>] --reason TEXT writes .factory/<n>/park.md with kind needs-human, and --question TEXT writes kind spec-gap, with ticket, kind, stage and parked_at in the front matter and the text as the body, exactly one non-empty flag being required
  - park resolves ticket n through worktree_for, or, when <n> is omitted, the session's own worktree, writes park.md in that ticket's worktree, and never writes state.json
  - the stage in park.md is the stage routing gives the ticket at that moment, or null when routing gives none or raises, and park still exits 0
  - park exits 0 when written, 2 on flag misuse, an empty text or no ticket, the same 2 or 3 the ticket lookup gives as factory next does, and 3 without writing when park.md already exists, naming the kind recorded, and docs/factory/design.md §9's park row lists these codes
  - read_chain(...).park returns the written front matter, and docs/factory/artifacts.md's park.md contract adds ticket and parked_at, and run.md's contract lists its fields
  - after load, save, update and render, git status --porcelain --ignored is unchanged in every ticket worktree of the test repository, and the full suite is green
specified_by: claude
specified_at: 2026-10-23
revised_after: spec-review.md (changes-requested, 11 findings)
---

# Spec: the factory loop's state outside the worktrees, and factory park

## Source

- Issue #219 (P1), and `docs/factory/design.md` §2, §4 rule 5, §6 and §9.
- The branch is stacked on #207 (PR #235) for `chain.common_dir`. `origin/dev` is merged in for #139's `LOOP_ARTIFACTS` and `Chain.park`.

## Shape

- **`factory/state.py`** holds `TicketState`, a frozen dataclass whose `cycles` is a read-only mapping and whose `log` is a tuple. Alongside it are `load`, `save`, `update`, `with_log` and `render_run_md`, plus `StateError`.
  - **`accepted`** is the factory loop's own acceptance record (design §4.5). #222 writes it, and `acceptance.md` is valid only when it matches.
  - **Writes.**
    - The temp file is `state.json.tmp-<pid>`; it is fsynced, then `os.replace`d.
    - On Windows, `os.replace` fails while any reader holds the file. The review measured 2897 of 3000 failures against a tight reader. Both sides retry `PermissionError` up to 50 times, 20 ms apart, then raise.
    - "Survives" means a killed process. fsync also covers power loss for the temp file. The directory entry is the OS's to sync.
  - **Locking.** `update` takes an exclusive OS lock on `state.lock` (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere), held for the read-change-write. Several processes write: `factory run` and #222's `feature new`, `spec submit` and `accept`. `load` takes no lock; it relies on atomic replace.
- **`factory park`** is registered in `COMMANDS`, and its handler is in cli.py.
  - `--reason` and `--question` are a required, mutually exclusive group.
  - It resolves the ticket the way `_next` does.
  - The stage comes from `routing.resolve`: null when the answer has no stage (a blocked row), or when it raises (`MalformedVerdict`).
  - `park.md` is written, not committed.

## Verification method: suite

**Red tests** (all new):
- the round trip, and the fresh state's exact values;
- `StateError` for each of missing, unknown and mistyped fields, a bad version, malformed JSON, and outside a repository;
- **the interrupted write.** A fake `os.replace` asserts that its source exists, sits in the same directory and holds the new state, then raises. Afterwards the old state reads back;
- a stale temp file holding a different valid state is ignored;
- `PermissionError` is retried, then raised, never read as missing;
- **two processes `update` concurrently** and both changes survive;
- the log only grows, and `cycles`/`log` are immutable;
- `render_run_md` is equal for differently ordered `cycles`;
- `park`: each flag, neither, both, empty text, outside a ticket, a second park (exit 3, nothing written), `<n>` from the primary checkout, a blocked chain and a malformed verdict (stage null, exit 0);
- the `git status --ignored` invariant.

## Decisions I made

- **A second park is exit 3, not 1.** A person or the loop decides what an existing park means. Exit 1 ("fix and re-run") would invite deleting it.
- **`attempt` is the number of the current dispatch, 1-based.** #218's `attempt_at_least = 2` therefore means the second dispatch.
- **Listing tickets' state** must take only numeric directory names under `<common>/factory/`, because #207's `sessions/` sits beside them. No function here lists tickets.

## Not in scope, with owner

- **Parking from a judge's detached snapshot** (#159): there, `park` alone exits 2, and `park <n>` would write into the ticket worktree, which `assert_untouched` forbids. The loop must give judges another way back.
- **The Designer's branch name** (#222): `issue/<n>-<slug>-design` parses as ticket n, so `park <n>` would see two worktrees. #222 must name it so it does not parse as a ticket branch. A comment is on #222.
- Routing reading `park.md` (#218), and pruning state for merged tickets (#210).
