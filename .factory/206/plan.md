---
ticket: 206
stage: build
radius:
  - factory/chain.py
  - factory/hooks.py
  - factory/cli.py
  - factory/merge.py
  - tests/test_factory/test_hooks.py
  - tests/test_factory/test_cli.py
  - docs/factory/stages.md
  - .factory/206/**
tasks: null
merge_order: null
proof:
  red_test: tests/test_factory/test_hooks.py::test_a_write_into_another_worktree_is_judged_there
  red_output_sha: see .factory/206/plan.md -> Proof
  suite: pass
docs_cleared: []
---

# Plan: resolve the gate from the file

## Radius

| Path | Why |
| --- | --- |
| `factory/chain.py` | **amended, see below** — `_git_dir` renamed to `git_dir` |
| `factory/hooks.py` | `governing`, `_always_writable`, `decide_write`, `session_report` |
| `factory/cli.py` | anchoring the target, enumerating worktrees, the Stop fold |
| `factory/merge.py` | nothing new joins the import closure, but the test is run to confirm rather than assumed |
| `tests/test_factory/test_hooks.py` | the fixture gains a `.git`; six tests change meaning |
| `tests/test_factory/test_cli.py` | the hook subcommand's end-to-end behaviour |
| `docs/factory/stages.md` | the claim that the gate refuses every edit outside `.factory/` |

**Not in the radius, deliberately:**

- `botting/`, `maple/`, `toolkit/` — nothing here reaches them.

## Radius amended, mid-build

The first version of this plan put `factory/chain.py` **outside** the radius,
on the reasoning that `_git_dir`, `current_branch` and `read_chain` are
imported rather than changed. That was wrong in the same sentence that said it:
the walk needs `_git_dir`'s logic, and `_git_dir` is private, so using it means
renaming it — which is changing `chain.py`.

Caught after making the edit, not before. The alternatives were to reimplement
the `gitdir:` pointer read in `hooks.py` (two copies of the one piece of logic
whose subtlety caused #199) or to widen the radius by one path for a rename
with no behaviour change. The rename is the smaller lie.

`read_chain` and `front_matter` are still untouched, and the exported name has
one call site plus the new one.
- `.claude/settings.json` — the matcher is #207's, not this ticket's. Touching
  it here would also put a privilege-escalation path in a PR about scoping
  (#202).
- `pyproject.toml`, `botting/`, `maple/` — nothing here reaches them.

## Order of work

1. `governing()` in `hooks.py`, with the walk's mechanics as the spec pins
   them, and its own tests first — it is the one piece everything else rests on.
2. `_always_writable(governing_root, target)`, resolved on both sides. Before
   `decide_write`, because getting this wrong reintroduces the #189 deadlock
   and I would rather see that fail in isolation.
3. `decide_write(target)`, and the jurisdiction table's three rows.
4. The fixture's `.git`, and the six tests that change meaning. **Run them
   against the old `decide_write` first** to confirm they invert as the review
   predicted, rather than taking its word for it.
5. Anchoring in `cli.py`: the event's `cwd`, then resolve.
6. The Stop fold: enumerate `<main>/.git/worktrees/*/HEAD`, `git status` per
   ticket worktree, refuse if any refuses.
7. `session_report`'s warning line.
8. `stages.md`.

## The shape

    def governing(target: Path) -> Governing | None
    def _always_writable(root: Path, target: Path) -> bool
    def decide_write(target: Path) -> Decision
    def decide_stop(repo_root, branch, source_changed) -> Decision   # unchanged
    def ticket_worktrees(repo_root: Path) -> tuple[Path, ...]        # cli.py

`decide_stop` keeps its signature on purpose: it stays the per-worktree
decision, and the fold that calls it once per worktree lives in `cli.py` where
the subprocess already lives. That keeps the pure function pure and leaves
every existing `decide_stop` test meaning what it meant.

## Proof

**`pytest`: 1170 passed, 3 skipped, 25 deselected.** 0 failed, 0 errors, 0
xfailed. ruff, ruff format and pyright clean. `tests/test_factory/` went from
217 to 241.

Four red-proofs, run separately because the change has four independent halves:

1. **Reverting `decide_write` to session-branch resolution: 9 red**, including
   `test_a_write_into_another_worktree_is_judged_there` (named above) and
   `test_a_cross_worktree_chain_write_is_never_refused`, which is the #189
   deadlock guard.
2. **Dropping the Stop fold and the anchoring: 2 red** — and this is where the
   plan was wrong. Only the *anchoring* tests failed. The three
   `_stop_everywhere` tests all stayed green, because they called the fold
   directly and pinned nothing about whether the hook uses it. **A gate is only
   as enforced as its call site.** Wrote
   `test_the_stop_hook_is_wired_to_the_fold_not_to_one_worktree`, through
   `main`, and it now goes red on that revert.
3. **Dropping `session=` at the write call site: 1 red.** Found the same way:
   the first revert broke nothing, because every other case is answered by row
   1. Row 2 is the row this design already lost once, so
   `test_the_pre_tool_use_hook_passes_the_session_so_row_two_survives` exists
   to notice it going a second time.
4. **The six tests the review predicted would invert** did invert, on the old
   `decide_write`, before the fixture gained its `.git`.

The lesson from 2 and 3 is the one worth keeping: testing a pure function and
testing that anything calls it are different tests, and the second is the one
that makes a gate real.

## What I expect not to be able to verify

- **That the gate fires in a live session.** `-m factory` loads the code from
  the process cwd, so a session in the main checkout runs the main checkout's
  `hooks.py`. This is inert in its own worktree until merged, and
  `test_hook_wiring.py` passes `cwd=ROOT`, so the suite cannot see it either.
  Suite-only evidence, and the PR body says so.
- **Whether the harness ever sends a relative `file_path`,** or carries `cwd`
  in this version's payload. Both are handled defensively; neither is observed.
- Nothing here touches the bot.
