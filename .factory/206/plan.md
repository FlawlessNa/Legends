---
ticket: 206
stage: build
radius:
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
  red_test: null
  red_output_sha: null
  suite: null
docs_cleared: null
---

# Plan: resolve the gate from the file

## Radius

| Path | Why |
| --- | --- |
| `factory/hooks.py` | `governing`, `_always_writable`, `decide_write`, `session_report` |
| `factory/cli.py` | anchoring the target, enumerating worktrees, the Stop fold |
| `factory/merge.py` | nothing new joins the import closure, but the test is run to confirm rather than assumed |
| `tests/test_factory/test_hooks.py` | the fixture gains a `.git`; six tests change meaning |
| `tests/test_factory/test_cli.py` | the hook subcommand's end-to-end behaviour |
| `docs/factory/stages.md` | the claim that the gate refuses every edit outside `.factory/` |

**Not in the radius, deliberately:**

- `factory/chain.py` — `_git_dir`, `current_branch` and `read_chain` are
  imported, not changed. `_git_dir` is private to that module and the walk
  needs its logic, so it is **exported rather than reimplemented**; if it needs
  changing, this plan is wrong and that is a different ticket.
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

Two things must be shown red, because the review predicted both:

1. **The six inverted tests.** Run the new tests against the *old*
   `decide_write` and confirm indifference — that is the bug, demonstrated.
2. **The cross-worktree case**, which is the ticket: two `tmp_path` worktrees,
   A complete and B missing `spec-review.md`, a write to source in B judged
   from a session rooted in A.

## What I expect not to be able to verify

- **That the gate fires in a live session.** `-m factory` loads the code from
  the process cwd, so a session in the main checkout runs the main checkout's
  `hooks.py`. This is inert in its own worktree until merged, and
  `test_hook_wiring.py` passes `cwd=ROOT`, so the suite cannot see it either.
  Suite-only evidence, and the PR body says so.
- **Whether the harness ever sends a relative `file_path`,** or carries `cwd`
  in this version's payload. Both are handled defensively; neither is observed.
- Nothing here touches the bot.
