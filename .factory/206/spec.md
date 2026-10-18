---
ticket: 206
stage: design
method: suite
criteria:
  - the governing worktree is found without invoking git, by reading the filesystem as current_branch already reads HEAD
  - a relative target is anchored on the event's cwd when present and the process cwd otherwise, then resolved, before anything else looks at it
  - with worktree A's chain complete and worktree B's missing spec-review.md, a write to source in B from a session rooted in A is refused and names B's ticket
  - a session on a ticket branch writing source outside its own worktree is still judged against its own chain, so the gate applies when either side is a ticket
  - a target under no git worktree is indifferent, because the factory governs this repository and not the filesystem
  - a worktree whose branch cannot be read is indifferent, deliberately, since there is no ticket to judge against
  - the always-writable set is evaluated against the governing root, resolved on both sides, so a cross-worktree chain or docs write is never refused
  - the Stop gate judges every linked worktree on a ticket branch, not only the session's, and refuses when any has source changed with no proof
  - a non-existent target or parent is not a resolution failure, and the walk terminates structurally rather than by hope
  - the session report says when the gates are live but the session is not in a ticket worktree
  - stages.md stops claiming the hook refuses every edit outside .factory/
specified_by: claude
specified_at: 2026-10-18
reviewed_by: claude (read-only reviewer, stand-in for #180)
---

# Spec: resolve the gate from the file, not the session

## Source

Issue #206, filed while reading `factory/hooks.py:70-104` for #163. Rewritten
against `spec-review.md`, which returned `changes-requested` with twelve
findings; four changed the design. The issue body is wrong in two places, both
corrected below and both flagged on the issue.

## The resolution

One new function, and every write decision goes through it:

    @dataclass(frozen=True)
    class Governing:
        root: Path
        branch: str | None
        ticket: int | None

    def governing(target: Path) -> Governing | None

It walks up from the resolved target looking for an **existing `.git` entry** -
a directory in the main checkout, a file holding `gitdir:` in a linked
worktree. The first ancestor holding one is the governing worktree; `None`
means the target sits under no worktree at all.

**The stop predicate is `(candidate / ".git").exists()`, not
`_git_dir(candidate) is not None`.** The two disagree: a worktree whose
`gitdir:` pointer is stale would be *walked past* by the second, and the walk
would then attribute the file to some ancestor checkout, or to nothing.
Stopping at the first `.git` and then failing to read a branch is the honest
outcome, and it routes to indifferent for a reason stated below.

**Without invoking git.** `PreToolUse` fires on every edit, so the worktree is
found by reading the filesystem, exactly as `current_branch` reads `HEAD`
rather than running git. The constraint is "no subprocess", not "walk upwards";
it comes from `intent.md`, and it is what this criterion pins.

### Normalising the target first

`_written_path` returns `Path(value)` verbatim from the tool input, and nothing
anchors it. A relative `file_path` then resolves against the **hook's** cwd -
the session's worktree, not the target's - and an unresolved `Path("foo.py")`
has `.parent == Path(".")`, whose parent is itself, so the walk terminates
immediately at the session's `.git`. Either way the original bug survives the
fix.

So, in order: **anchor, resolve, then walk.** A relative target is anchored on
the `cwd` field of the harness event when present - `_read_stdin` already reads
the envelope and `_written_path` throws that field away - and on the process cwd
otherwise. Then `resolve()`, non-strict.

### The walk's mechanics, pinned rather than left open

- **A non-existent target or parent is not a resolution failure.** This is the
  normal `Write` case: `<worktree>/.factory/207/intent.md` in a fresh chain.
  `(missing / ".git").is_dir()` is simply `False` and `read_text` raises
  `OSError`, which the walk treats as "not here, keep going".
- **Termination is structural.** Iterate `[resolved, *resolved.parents]`, which
  is finite. `while True: p = p.parent` does not terminate - on Windows
  `Path("C:/").parent` is itself.
- **Resolved on both sides.** `_always_writable` resolves the target; it must
  resolve the governing root too, or Windows case-folding and 8.3 short names
  make `relative_to` raise and the chain write gets judged - the #189 deadlock,
  back through a side door.
- **Symlinks and junctions are followed**, since `resolve()` follows them. A
  target reached through a junction is judged against the real worktree, which
  is what we want.
- **A submodule stops at its own `.git`**, whose `HEAD` is typically detached,
  so submodule source escapes the gate. There is no `.gitmodules` here today;
  this sentence exists so it is not a surprise later.

## Why resolve rather than refuse

The issue offered a second option: refuse any write outside the session's repo
root. Rejected. Refusing bans a workflow; resolving enforces the right rule on
it. A write into worktree B from a session in worktree A is not inherently
wrong - what was wrong was judging it against A's chain. Refusing would also
bind the maintainer, who legitimately edits across checkouts, and would teach
everyone to set `FACTORY_HOOKS=off`.

## Jurisdiction

The gate applies when **either side is a ticket**:

| Target's worktree | Session | Judged against | Why |
| --- | --- | --- | --- |
| on a ticket branch | anything | **the target's chain** | the fix |
| no ticket, or no worktree | on a ticket branch | **the session's chain** | a Builder is accountable for what it writes anywhere |
| no ticket, or no worktree | not a ticket | indifferent | nothing to judge |

The first draft had only the first and third rows, and called the missing
middle one "today's behaviour, and correct". It is the opposite: a
ticket-branch session writing source into the trunk checkout is refused today
and would have been **allowed** - a loosening the draft asserted it was not
making. The rule above is stronger than today and stronger than the draft.

### Where jurisdiction ends

**The issue body is wrong where it says "an unresolvable target must fail
closed".** Read literally that refuses every write to a scratchpad file or a
temp directory - noisy, and none of the factory's business. The factory governs
this repository, not the filesystem.

**And the body's fail-closed case does not exist.** It imagined a chain that
could not be read, but `read_chain` cannot fail: `is_file()` swallows
`OSError`, `front_matter` catches it and returns `{}`, and the docstring is the
contract - *"Missing files are absent, never an error."* Absent is already
refused, with a better message. So there is nothing to fail closed on, and the
draft's fourth row is deleted rather than implemented behind a mock.

The one reachable degraded case is a worktree whose `.git` exists but whose
branch cannot be read - a stale `gitdir:`, a detached `HEAD`. **Indifferent,
deliberately:** a detached `HEAD` is a legitimate state, and with no ticket
there is nothing to fail closed *to*. Stated so it is a decision rather than an
accident.

## `decide_write`'s signature

`decide_write(target: Path) -> Decision`. Both `repo_root` and `branch` become
dead once resolution comes from the target, and a function that ignores two of
its three arguments is worse than one that does not take them.

**This inverts six currently-green tests**, and the first draft did not say so.
The `repo` fixture is a `tmp_path` with no `.git` at any level, so `governing()`
returns `None` and every write-gate test falls to indifferent:
`test_source_is_refused_before_a_spec_exists`,
`test_source_is_refused_while_the_spec_is_unreviewed`,
`test_source_is_still_inside_the_gate` (three parametrisations) and
`test_the_reason_names_the_override`.

The fixture gains a real `.git/HEAD`. That is not a workaround: those tests
currently pass a fabricated branch string *past* the resolution they are meant
to exercise, and afterwards they exercise it. Baseline to beat: `217 passed` in
`tests/test_factory/`.

## The Stop gate

`_source_changed` runs `git status --porcelain` in the session's `repo_root`.
The first draft kept that and called it "correct for Stop". It is not merely
narrow - in the workflow this ticket exists to govern it is **dead**: the
session sits in the main checkout, `ticket_from_branch` returns `None`, and
`decide_stop` returns `INDIFFERENT` for every turn, forever. The proof gate is
the one that stops an agent finishing without a test, so deferring it is
deferring the point.

`Stop` fires once per turn, so the budget is there:

- The CLI enumerates worktrees by reading `<main>/.git/worktrees/*/HEAD`, plus
  the session's own root. No `git worktree list` - same no-subprocess habit,
  and this is a directory listing.
- For each worktree on a ticket branch, `git status --porcelain` in that
  worktree. One subprocess per ticket worktree, once per turn.
- `decide_stop(repo_root, branch, source_changed)` **keeps its signature** and
  stays the per-worktree decision. A fold above it refuses if any worktree
  refuses, so the pure function stays pure and the existing tests keep their
  meaning.

## The session report

`session_report` reads the session's branch, so for the very workflow this
governs it prints the heartbeat and nothing else - while writes into ticket
worktrees start being refused. That drops the "removes *I did not know*"
property of #199 and #202 exactly when it starts to matter. One line when the
gates are live and the session is not in a ticket worktree.

## Documentation

`stages.md` claims the `PreToolUse` hook "refuses every edit outside
`.factory/`". That has never been true - `docs/`, `AGENTS.md` and `CLAUDE.md`
are exempt, pinned by `test_documentation_is_outside_the_gate` - and it is
about to become more wrong. Corrected, not preserved. The issue asked for this
and the first draft dropped it, because the radius is files and acceptance is
not the radius.

## What cannot be verified before merge

`-m factory` resolves the code from the process cwd, so a session rooted in the
main checkout runs the **main checkout's** `hooks.py`. The new gate is inert in
its own worktree until this merges, and `test_hook_wiring.py` passes `cwd=ROOT`
explicitly, so the suite cannot see the divergence either.
`CLAUDE_PROJECT_DIR` picks the script and the interpreter, not the cwd, so it
does not change the answer. **Cross-worktree judgement is therefore suite-only
evidence until merged**, and the PR body must say so.

## What this does not do

- Does not add roles. #163 does, on top of this.
- Does not make the gates unevadable. `FACTORY_HOOKS=off` still works by
  design - **and it is not the only hole:** the `PreToolUse` matcher covers
  `Write|Edit|MultiEdit|NotebookEdit`, so a shell redirection bypasses every
  gate. Pre-existing, out of scope, filed as #207 so #163 does not
  inherit a false sense of closure.
- Does not change which rules the gates enforce, with one stated exception:
  the middle row of the jurisdiction table restores enforcement the first draft
  would have dropped.
- Does not catch a submodule write.

## Radius

Named in `plan.md`, not here.
