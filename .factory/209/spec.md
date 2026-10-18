---
ticket: 209
stage: design
method: suite
criteria:
  - the primary checkout is identified structurally, and a test renames the trunk branch to prove no branch name is involved
  - a source write in the primary checkout is refused, whatever branch it is on and whatever the session is
  - each exemption is allowed in the primary checkout, one test per exemption
  - configs/maps/** is refused there despite configs/** being exempt, because it is a hard-stop path
  - maple/launchers/** is refused there, because a launcher imports the engine and is source
  - a write inside a linked ticket worktree is unaffected, preserving #206
  - the rule is one constant and one call site, asserted by a test that fails if the refusal becomes reachable another way
  - a target under no git worktree is indifferent whatever the session, which corrects an over-reach in #206
  - the refusal names the exemptions and a command that exists today
  - AGENTS.md, the SessionStart report and stages.md all carry the rule, and a test asserts the report carries it in the primary checkout
specified_by: claude
specified_at: 2026-10-18
reviewed_by: null
---

# Spec: refuse source writes in the primary checkout

## Source

Issue #209, body amended before building to correct the exemption list:
`maple/launchers/**` out, `profiles/**` and `toolkit/**` in.

## Identifying the primary checkout

Structural, with no branch name anywhere:

    def is_primary(root: Path) -> bool:
        found = git_dir(root)
        return found is not None and found.parent.name != "worktrees"

A linked worktree's `.git` is a *file* holding
`gitdir: <primary>/.git/worktrees/<name>`, so its resolved git dir sits under
`worktrees/`. The primary checkout's `.git` is a directory and does not.
`factory/cli.py:ticket_worktrees` already distinguishes them this way; this
reuses the reasoning rather than inventing a second one.

The first draft keyed off "the working branch" and named
`movements-improvements`. That was wrong, and the correction is the
load-bearing part of this ticket: renaming the trunk, or moving the factory's
base from `movements-improvements` to `dev`, must change nothing. A test
renames the branch and asserts the verdict is identical.

## What is refused, and what is not

**Refused:** everything not named below. `botting/`, `maple/` (launchers
included), `factory/`, `tests/`, `scripts/`, `ml_training/`, `conftest.py`,
`paths.py`, `pyproject.toml`.

**Exempt**, beyond the universal exemptions that already exist
(`.factory/**`, `docs/**`, `AGENTS.md`, `CLAUDE.md`):

| Path | Why |
| --- | --- |
| `configs/**` *except* `configs/maps/**` | the settings passed into a launcher; `factory-models.toml` is policy meant to change without a ticket |
| `profiles/**` | the other half of a launcher's input |
| `toolkit/**` | standalone scripts, run directly, imported by nothing |

### `configs/maps/**` is carved out, and it costs nothing

Map JSON is on the hard-stop list (`AGENTS.md`): recorded data that movement
depends on, not a setting anyone tunes, and among the few things no offline
test can check. Exempting it would make the primary checkout the easiest place
to change the one thing nobody can verify.

The carve-out is also free, which is what makes this an easy decision rather
than a trade. Maps are authored through the GUI editor in
`maple/model/mechanics/minimap_creation/`, a running Python program writing
files directly, and the write gate only ever sees an agent's tool calls. So
refusing `configs/maps/**` here blocks an agent hand-editing recorded data and
does not touch the way maps are actually made.

### `maple/launchers/**` is not exempt

An earlier draft had it, from misreading "configs/launchers" as the launcher
modules. A launcher imports the engine and can change what reaches the game,
which is the category this gate exists for. The *configuration* it reads is
`configs/` and `profiles/`, and those are exempt.

### `toolkit/**` is exempt for the opposite reason to everything else

Nothing imports it, it is run by hand, and `AGENTS.md` already treats it as its
own category. This changes only **where** it may be edited; it stays on the
same lint and typing gates, and a real `toolkit/` change still belongs in a
ticket.

## Where the rule sits in the order

`decide_write` gains one row, and **its position is the whole design**:

| | Condition | Verdict |
| --- | --- | --- |
| 1 | the target's worktree is on a ticket branch | judged against that chain |
| 2 | **the target is in the primary checkout and is not exempt** | **refused** |
| 3 | the session is on a ticket branch, and the target is in the repo | judged against the session's chain |
| 4 | otherwise | indifferent |

**Row 2 must precede row 3.** If the session's ticket were consulted first, a
Builder with a complete chain would be *allowed* to write the primary
checkout's source — and a Builder's radius lives in its own worktree, so that
is never right. Nobody writes primary-checkout source: not an orchestrator, not
a Builder with a perfect chain, not the maintainer without `FACTORY_HOOKS=off`.

Row 1 still precedes it, because a path inside a ticket worktree is governed by
that ticket however the primary checkout feels about it.

## A correction to #206, flagged rather than smuggled

#206's session row fires for **any** target, including one under no git
worktree at all. `_judge` then calls `_always_writable(session_root, target)`,
which raises `ValueError` for a path outside the repo and returns `False`, so
the chain is consulted — and a write to a **scratchpad or temp file** is
refused whenever the session's chain is incomplete.

That contradicts #206's own stated principle, which this spec keeps:

> The factory governs this repository, not the filesystem.

It is live today: an agent on a fresh ticket cannot write a temp file until its
spec exists, for no reason anyone intended. Row 4 therefore applies whenever
the target is under **no worktree**, whatever the session is, and row 3 narrows
to targets inside the repository.

This is a **behaviour change beyond the ticket's title**, so it is named here,
in the PR body, and in a test of its own rather than folded in quietly.

## One constant, one call site

The maintainer is trying this provisionally:

> "I'm willing to accept this friction, at least for a couple of days/weeks,
> and see if I want to revert it sometime later or not."

So reverting must be deleting one row and one constant, with one test going
red. A test asserts the refusal is reachable by exactly one path — if a second
call site ever grows, the suite says so. A rule threaded through three places
does not get reverted; it gets `FACTORY_HOOKS=off`-ed, and that disables every
other gate with it.

## Every agent must know before it is refused

Three places, and they are not redundant — only one puts the rule in context
*before* the agent acts:

1. **The `SessionStart` report.** One line when the session is in the primary
   checkout, in the slot #202 established. This is the mechanism; the rest are
   lookups an agent must choose to make.
2. **`AGENTS.md`** — the canonical, tool-neutral statement, read natively by
   Claude Code and by convention elsewhere.
3. **`docs/factory/stages.md`** — beside the other `[mechanical]` markers.

Plus **the deny reason**, which is self-contained: what is refused, what is
exempt, and what to do instead, so an agent that hits it anyway needs no second
lookup.

The `factory` skill needs no change: it is entered on a ticket branch, where
this rule does not apply.

## The way forward must exist today

`factory claim` (#147) is not built, so the refusal names what works now:

    git worktree add ../<slug> -b issue/<n>-<slug>

with `herdr worktree create --branch issue/<n>-<slug>` as the alternative for
whoever uses it. The reason reads the **current** branch for the base rather
than naming one, for the same reason the anchor is structural.

## What this does not do

- Does not add roles. #163 sits on this floor.
- Does not catch a write through the shell (#207) — and it makes that hole
  matter more, since the primary checkout is where a shell is handiest.
- Does not enforce the hard-stop list generally. `configs/maps/**` is refused
  here as a consequence of this rule, not as hard-stop enforcement; that stays
  with the merge policy.
- Does not stop the maintainer. `FACTORY_HOOKS=off` is the documented escape:
  this is a floor, not a lock.

## Radius

Named in `plan.md`, not here.
