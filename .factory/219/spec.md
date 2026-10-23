---
ticket: 219
stage: design
method: suite
criteria:
  - factory/state.py stores one ticket's state at <git-common-dir>/factory/<n>/state.json, where the common dir comes from chain.common_dir, so every worktree of the repository reads the same file
  - the state holds version, ticket, stage, attempt, cycles (a mapping from judged stage to a count), worker (name, role, started_at, or null), turn_base, submitted, parked (kind and reason, or null), designer_session and an append-only log of entries each with at, event and detail
  - reading a ticket with no state.json returns a fresh state for that ticket, and reading a file whose version is not 1, or whose JSON is malformed, raises StateError naming the file
  - save writes a temporary file in the same directory and replaces state.json with os.replace, so a write interrupted after the temporary file is written leaves the previous state readable, and a stale temporary file never shadows state.json
  - a state saved and loaded again is equal to the original, field for field
  - appending to the log never rewrites or reorders earlier entries
  - render_run_md(state) returns the same text for the same state, with front matter holding ticket, stage, attempt and the cycles, and a body table of the log in order
  - factory park [<n>] --reason TEXT writes .factory/<n>/park.md with kind needs-human, and --question TEXT writes kind spec-gap, each with ticket, kind, stage and parked_at in the front matter and the text as the body, exactly one of the two flags being required
  - park resolves the ticket from <n> through worktree_for, or from the session's own branch when <n> is omitted, and writes in that ticket's worktree
  - park exits 2 outside any ticket, and exits 1 without writing when park.md already exists, naming the kind already recorded
  - the stage recorded in park.md is the stage routing gives the ticket at that moment
  - read_chain(...).park returns the written front matter, and docs/factory/artifacts.md's park.md contract lists ticket, kind, stage and parked_at
  - nothing in this ticket writes into a ticket worktree except park.md, and the full suite is green
specified_by: claude
specified_at: 2026-10-23
---

# Spec: the factory loop's state outside the worktrees, and factory park

## Source

Issue #219 (P1), and `docs/factory/design.md` §4 rule 5 and §6. The branch is
stacked on #207 (PR #235), whose `chain.common_dir` this uses.

## Shape

- **`factory/state.py`.** `TicketState`, a frozen dataclass, with `load(repo_root, ticket)`, `save(repo_root, state)` and `with_log(state, event, detail)`, plus `render_run_md(state)` and `StateError`.
  - No locking: one `factory run` at a time is #159's OS lock. Atomic replace is what protects a reader from a half-written file.
  - The temp file is `state.json.tmp-<pid>` in the same directory. `load` reads only `state.json`.
- **`factory park`** is registered in `COMMANDS`, and its handler is in cli.py.
  - `--reason` and `--question` are a required, mutually exclusive group.
  - The stage comes from `routing.resolve` on the ticket's worktree.
  - `park.md` is written, not committed. `.factory/` writes are always allowed, and committing is the worker's or the loop's job.

## Verification method: suite

**Red tests** (all new; nothing exists today):
- the state round trip;
- a fresh state for a missing file;
- `StateError` for a bad version and for malformed JSON;
- an interrupted write, simulated by raising inside `os.replace` after the temp file is written, leaving the old state readable;
- a stale temp file ignored;
- the log only appends;
- `render_run_md` is deterministic;
- `park` with each flag, with neither, and with both;
- `park` outside a ticket gives exit 2, and a second `park` gives exit 1;
- `park` with `<n>` from the primary checkout writes in ticket n's worktree.

## Decisions I made

- **A second park is refused, not overwritten.** Un-parking is the maintainer's or the loop's act. A worker re-parking should see that it is already parked.
- **`state.json` carries a version from day one,** so #159 can migrate it rather than guess.
- **The roles allowlist for `park` waits for #218's `roles.py`.** Every role may park, so nothing is lost meanwhile.

## Not in scope

- Routing reading `park.md` (#218).
- The loop's dispatch (#159).
- Pruning `state.json` for merged tickets (#210).
