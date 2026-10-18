---
ticket: 206
stage: design
method: suite
criteria:
  - the governing worktree is resolved by walking up from the target to the nearest .git, with no subprocess
  - the branch and the chain are read from the target's worktree, not the session's
  - a write into a ticket worktree from a session on a non-ticket branch is judged, not waved through
  - a write judged against the chain of the target's worktree when the two worktrees differ
  - a target under no git worktree at all is indifferent, because the factory governs the repo and not the filesystem
  - a target inside a ticket worktree whose chain cannot be read is refused, so the one place with jurisdiction fails closed
  - decide_stop sees source changes in the worktree it is judging, not only in the session's
  - the always-writable set is evaluated relative to the target's worktree, so the chain and docs stay writable cross-worktree
  - the hook's own resolution never raises, because a hook that throws is a hook that blocks every edit
specified_by: claude
specified_at: 2026-10-18
reviewed_by: see spec-review.md
---

# Spec: resolve the gate from the file, not the session

## Source

Issue #206, filed while reading `factory/hooks.py:70-104` for #163. The body is
accurate except on one point, corrected below under **Jurisdiction**.

## The resolution

One new function, and every decision goes through it:

    @dataclass(frozen=True)
    class Governing:
        root: Path          # the worktree the target lives in
        branch: str | None
        ticket: int | None

    def governing(target: Path) -> Governing | None

It walks up from the target's parent looking for a `.git` entry — a directory
in the main checkout, a file holding `gitdir:` in a linked worktree, which
`chain._git_dir` already knows how to read. The first one found is the
governing worktree. `None` means the target is under no worktree at all.

**No subprocess.** `PreToolUse` fires on every edit, so the worktree is found
by reading the filesystem, exactly as `current_branch` reads `HEAD` rather than
running git. The walk is bounded by the filesystem root and costs a `stat` per
level.

## Why resolve rather than refuse

The body offered a second option: refuse any write outside the session's repo
root. Rejected, and worth recording why.

Refusing bans a workflow; resolving enforces the right rule on it. A write into
worktree B from a session in worktree A is not inherently wrong — what is wrong
is judging it against A's chain. Once the gate reads B's chain, the write is
allowed exactly when B's artifacts are in place, which is the rule the factory
actually has. Refusing would also bind the maintainer, who legitimately edits
across checkouts, and would teach everyone to switch `FACTORY_HOOKS=off`.

## Jurisdiction

**The ticket body is wrong where it says "an unresolvable target must fail
closed".** Read literally that refuses every write to a scratchpad file, a
temp directory or anything else off-tree — noisy, and none of the factory's
business. The factory governs this repository, not the filesystem.

The line this spec draws:

| Target | Answer | Why |
| --- | --- | --- |
| Under no git worktree | **indifferent** | outside the factory's remit entirely |
| In a worktree on a non-ticket branch | **indifferent** | today's behaviour, and correct |
| In a ticket worktree, chain readable | **judged** against *that* chain | the fix |
| In a ticket worktree, chain unreadable | **refused** | the one place with jurisdiction fails closed |

Failing closed only where there is jurisdiction is the whole of the
correction. A gate that cannot tell whose ticket a file belongs to must not
wave it through — but a path it has no business judging is not the same thing
as a path it failed to judge.

Note the contrast with `.claude/hooks/factory-hook.sh`, which fails **open** on
purpose: it resolves an *interpreter*, and a session with no Python is a session
that cannot work at all. This resolves *jurisdiction*, which is the opposite
case.

## The always-writable set moves with the target

`_always_writable` currently computes `target.relative_to(repo_root)` against
the **session's** root, so a write to `<worktree-B>/.factory/206/spec.md` from
a session in the main checkout raises `ValueError` and is not recognised as
always-writable. It must be evaluated against the **governing** root, or the
first thing the new gate refuses is the artifact write that would satisfy it —
the same deadlock review caught in #189, reintroduced by the fix for a
different bug.

## `decide_stop`

`_source_changed` runs `git status --porcelain` in the session's `repo_root`.
That is the one place a subprocess is affordable, because `Stop` fires once per
turn — but it looks in the wrong tree.

`decide_stop` keeps its signature and `source_changed` stays a parameter, so
the pure function stays pure; the caller in `cli.py` is what must run `git
status` in the governing worktree. Since `Stop` carries no target path, the
governing worktree for a Stop decision is the session's own — which is correct
for `Stop` and wrong only for `PreToolUse`. **What this ticket changes for
`decide_stop` is therefore narrow:** it is judged against the session's
worktree, and that is now a stated decision rather than an accident.

A session that edits another worktree and then stops is still not caught by the
proof gate. That is a real remaining hole and this spec says so rather than
implying otherwise; closing it needs the Stop hook to know which worktrees the
turn touched, which nothing records today. **Named for a follow-up, not fixed
here.**

## What this does not do

- Does not add roles. #163 does, on top of this.
- Does not make the gates unevadable. `FACTORY_HOOKS=off` still works, by
  design.
- Does not change which rules the gates enforce — only which chain they are
  enforced against.
- Does not close the `decide_stop` cross-worktree hole described above.

## Radius

Named in `plan.md`, not here.
