---
ticket: 206
stage: design
verdict: changes-requested
reviewed_by: claude (read-only reviewer, stand-in for #180)
reviewed_at: 2026-10-18
criterion_quoted: "decide_stop sees source changes in the worktree it is judging, not only in the session's"
---

# Spec review: resolve the gate from the file

**Verdict: `changes-requested`.** The core move is right and the two rejections
recorded in the first draft were better reasoning than the issue body. But the
draft had an outright internal contradiction, a hole that reintroduced the bug
it was fixing, and it was silent on the thing that would cost the Builder most.
It also loosened enforcement in a direction nobody agreed to, while asserting
it changed nothing.

Twelve findings. Four changed the design.

## The four that changed the design

### 1. Criterion 7 contradicted the body, and the body's claim was false

The criterion said `decide_stop` sees changes in the worktree it is judging.
The body said the governing worktree for a Stop decision *is* the session's
own, and named the cross-worktree case as a follow-up. Read against the body
the criterion is self-satisfying - the existing `_source_changed(Path.cwd())`
already meets it unmodified; read literally it demands the work the body
defers. A Builder would have implemented the cheap reading, and Review would
have ticked a criterion that pinned nothing.

Worse, the body's "correct for Stop" was not narrow but **false**:

> `factory/cli.py:318` sets `repo_root = Path.cwd()`, and
> `.claude/hooks/factory-hook.sh:36` is `exec "$python" -m factory hook
> "$event"` with **no `cd`**. In the workflow `intent.md` itself describes as
> the one every ticket was built under, `Path.cwd()` is the main checkout,
> `ticket_from_branch` returns `None`, and `decide_stop` returns `INDIFFERENT`
> - for every turn, forever.

So the proof gate - the one that stops an agent finishing without a test - is
dead in the primary workflow. Deferring that is deferring the gate this ticket
is about.

**Decided: fixed, not deferred.** `Stop` fires once per turn, so the subprocess
budget is there for one `git status` per ticket worktree. The CLI enumerates
every linked worktree on a ticket branch, plus the session's own, and the
decision refuses if any of them has source changed with no proof recorded.
`decide_stop` keeps its per-worktree signature and a fold sits above it, so the
pure function stays pure and the existing tests keep their meaning.

### 2. Nothing normalised the target path

`_written_path` returns `Path(value)` verbatim from the tool input. A relative
`file_path` then resolves against the **hook's** cwd, which is the session's
worktree and not the target's - and an unresolved `Path("foo.py").parent` is
`Path(".")`, whose parent is itself, so the walk terminates immediately at the
session's `.git`.

> Concrete input: session cwd is the main checkout on `movements-improvements`,
> the model emits `Write{"file_path": "factory/hooks.py"}` intending the ticket
> worktree. Governing root resolves to the main checkout, branch is non-ticket,
> verdict `INDIFFERENT`. **That is bug 1 from the issue body, surviving the fix.**

The reviewer also noticed the `PreToolUse` payload carries a `cwd` field that
`_read_stdin` reads and `_written_path` throws away.

**Decided:** a relative target is anchored on the event's `cwd` when present,
else the process cwd, and resolved before the walk. New criterion; there was
none covering normalisation at all, which is how this would have shipped broken
and green.

### 3. Row 2 of the jurisdiction table loosened enforcement

The draft routed "target in a worktree on a non-ticket branch" to indifferent
and called it "today's behaviour, and correct". It is not today's behaviour for
the symmetric case:

> Session cwd is the ticket worktree; the agent writes to the trunk checkout's
> `botting/core/engine.py`. **Today:** judged against ticket 206's chain, and
> refused for want of `spec-review.md`. **After the draft:** governing root is
> the main checkout, no ticket, allowed.

A Builder mid-ticket would have gained the ability to write source straight
into the trunk, unjudged, which it cannot do today - while the draft's "what
this does not do" asserted it changed only which chain the rules were enforced
against.

**Decided:** the gate applies when **either** side is a ticket. The governing
worktree on a ticket branch wins; failing that, a session on a ticket branch is
judged against its own chain. That is stronger than today *and* stronger than
the draft, and it matches the intent: a Builder mid-ticket is accountable for
everything it writes, wherever it writes it.

### 4. Row 4 was unreachable, so the fail-closed design was fiction

`read_chain` cannot fail - `is_file()` swallows `OSError`, `front_matter`
catches it and returns `{}`, and the docstring is the contract: *"Missing files
are absent, never an error."* There is no constructible state that is
"unreadable" rather than "absent", and absent is already refused with a better
message. Every degraded path lands elsewhere: no `.git` is row 1, a stale
`gitdir:` or an unreadable `HEAD` is row 2, a denied `stat` is row 1.

> Row 4 fails closed where nothing can happen and fails open where something
> can.

**Decided:** row 4 and its criterion are **deleted**, and the spec says the
issue body's fail-closed item rested on a condition that cannot occur. The one
genuinely reachable degraded case - a worktree whose branch cannot be read -
stays indifferent, deliberately: a detached `HEAD` is a legitimate state and
there is no ticket to fail closed *to*.

## Acted on, as specified

### 5. The signature was unstated, and six tests invert

The draft was explicit that `decide_stop` keeps its signature and silent about
`decide_write(repo_root, branch, target)`, both of whose first two parameters
become dead once resolution comes from the target. And the `repo` fixture is a
`tmp_path` with no `.git` anywhere, so `governing()` returns `None` and six
currently-green tests would have inverted to indifferent - against a baseline
of `217 passed`, with the draft's "what this does not do" listing four things
and not this one.

**Decided:** `decide_write(target)` takes the target alone. The fixture gains a
real `.git/HEAD`, which makes those tests exercise the real resolution instead
of a fabricated branch string - strictly better tests. Stated in the spec,
because a `method: suite` spec that does not name the suite it breaks has not
costed itself.

### 6-7. The walk was underspecified in exactly the cases that matter

The stop predicate was left open, and the two obvious choices disagree once a
worktree is nested inside a checkout. The mechanics were one sentence, and
three of the four gaps bite the common case - above all **a target whose parent
does not exist, which is the normal `Write` case**: done naively, every
new-file write becomes indifferent, or under a fail-closed reading, refused.

The reviewer checked the one thing that makes it workable: `Path.resolve()` on
Windows does **not** raise for a non-existent path.

**Decided and now pinned:** stop at the first ancestor holding an existing
`.git` entry; resolve non-strictly first and iterate `[resolved, *parents]`, so
termination is structural rather than hoped for; a non-existent target or
parent is not a resolution failure; `_always_writable` compares resolved to
resolved, because comparing an unresolved root to a resolved target brings the
#189 deadlock back through Windows case-folding; symlinks are followed, so a
target reached through a junction is judged against the real worktree.
Submodules get a sentence: they stop at their own `.git` with a detached
`HEAD`, so submodule source escapes the gate. No `.gitmodules` today; it would
have been a surprise later.

### 8. The deliverable is unverifiable before merge

`-m factory` resolves the code from the process cwd, so a session rooted in the
main checkout runs the **main checkout's** `hooks.py`. The new gate is inert in
its own worktree until merged, and `test_hook_wiring.py` passes `cwd=ROOT`
explicitly, so the suite cannot see the divergence either.

**Decided:** said in the spec and carried to the PR body. `CLAUDE_PROJECT_DIR`
chooses the script and the interpreter, not the cwd, so it does not change the
answer.

### 9. The first time the new gate fires, the session has had no warning

`session_report` still reads the session's branch, so for the very workflow
this ticket governs it prints the heartbeat and nothing else - while writes
into ticket worktrees start being refused. That drops the "removes *I did not
know*" property of #199 and #202 at the moment it starts to matter.

**Decided:** when the gates are live and the session is not in a ticket
worktree, the report says so in one line. New criterion.

### 10. An accepted acceptance item was dropped

The issue asked for `stages.md` and `docs/agents/*` corrected wherever they
imply the gates bind by branch alone, and no criterion covered it; the radius
is files, not acceptance. The reviewer also found the doc already wrong:
`stages.md:144-145` claims the hook "refuses every edit outside `.factory/`",
which `docs/` and `AGENTS.md` have always contradicted.

**Decided:** criterion added, and the existing error fixed rather than
preserved.

### 11. `reviewed_by` was pre-filled, pre-clearing the block it exists to impose

`artifacts.md` contracts `reviewed_by` as `string | null` with *"`null` blocks
stage 3"*, and the Specifier had written `see spec-review.md` before any review
existed. Small, and the reviewer put it exactly right: *"this is a repo whose
entire thesis is that sequence is mechanical rather than remembered, and this
is the Specifier hand-filling the reviewer's field."*

**Decided:** `null` until a reviewer sets it. **This was a standing habit, not
a one-off** - #140 and #162 both carry the same pre-filled string. Corrected
from here on; the two earlier chains are left as they are rather than
rewritten, and this note is the record.

### 12. `FACTORY_HOOKS=off` is not the only evasion

The `PreToolUse` matcher covers `Write|Edit|MultiEdit|NotebookEdit`, so a
shell redirection bypasses every gate. Pre-existing and out of scope, but the
draft named one hole and implied it was the only one.

**Decided:** second clause added, and filed as #207 so #163 does not inherit
a false sense of closure.

## Criteria, after the rewrite

The reviewer judged 2, 5 and 8 sound; 1, 4 and 9 in need of rewording into
decidable outcomes; 3 a duplicate of 4; 7 self-satisfying; 6 unreachable. All
acted on. Two criteria were added for the gaps that had none - path
normalisation, and the ticket-session-writes-to-trunk case - which were the two
highest-cost findings.

Criterion 1 drew a fair objection worth recording: it specified a *mechanism*,
so a correct implementation using `git rev-parse` would have failed it while a
broken walk-up passed. Rewritten as the outcome plus the real constraint, which
is "without invoking git" - that one comes from `intent.md` and stays.

## What the review could not check

- The actual cwd the harness hands the hook. It established that nothing in the
  chain changes it, but could not observe a live invocation.
- Whether this harness version's `PreToolUse` payload carries `cwd`. The spec
  therefore treats it as optional and falls back to the process cwd.
- Whether the harness ever delivers a relative `file_path`. The `Write` schema
  demands absolute, but `PreToolUse` fires on raw tool input before validation.
  The spec is robust to it either way; anchoring costs three lines.
- The walk's cost at real depth against the hook's 10s budget.
- `plan.md`, which did not exist yet, so it could not confirm the radius covers
  `tests/test_factory/test_hooks.py`. It does.
