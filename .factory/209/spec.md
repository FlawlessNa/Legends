---
ticket: 209
stage: design
method: suite
criteria:
  - the refusal requires identity, so another repository's checkout on this machine is never refused
  - a linked worktree is never the primary checkout, established by .git being a file rather than by any path name
  - a repository whose own directory is named worktrees is still correctly identified as primary
  - a source write in the primary checkout is refused whatever branch it is on, including a ticket branch with a complete chain
  - each exemption is allowed in the primary checkout whatever the session is, and short-circuits rather than falling through
  - the primary-checkout exemptions do not apply inside a ticket worktree, so the artifacts-before-code gate keeps every tree it has today
  - configs/maps/** is refused in the primary despite configs/** being exempt
  - .claude/settings.local.json is writable in the primary, since the refusal names it as the escape hatch
  - forcing the single predicate off removes every primary-checkout refusal and leaves every other gate test green
  - a target under no git worktree is indifferent whatever the session, correcting an over-reach in #206
  - the named tests that change meaning do so with the stated reasons, and the session row keeps a regression detector
  - OFF_TICKET no longer says the gates apply only to files in a worktree, and both report paths carry the rule
specified_by: claude
specified_at: 2026-10-18
reviewed_by: claude (read-only reviewer, stand-in for #180)
---

# Spec: refuse source writes in the primary checkout

## Source

Issue #209, body amended before building (exemption list), then **rewritten
against `spec-review.md`**, which returned `changes-requested` with eleven
findings. Two broke the design. Where this spec and the issue disagree, this
spec is right and the review says why.

## Identifying the primary checkout needs identity, not shape

The draft proposed `git_dir(root).parent.name != "worktrees"`. That fires on
**every git repository on the machine**: another project's checkout is refused,
with a reason telling the agent to create a worktree in the Legends factory.
#206 exists because agents write other checkouts by absolute path, so that is
reachable rather than theoretical.

Two conditions, both required:

    def _is_primary(root: Path) -> bool:
        """A linked worktree's `.git` is a FILE holding a gitdir: pointer."""
        return (root / ".git").is_dir()

    def _common(root: Path) -> Path | None:
        """The shared git directory: the identity of a repository."""
        found = git_dir(root)
        if found is None:
            return None
        return found.parent.parent if found.parent.name == "worktrees" else found

The refusal fires only when the target's worktree is primary **and**
`_common(target_root) == _common(session_root)`. Verified against four real
roots:

| Root | primary? | same repo? | refuse? |
| --- | --- | --- | --- |
| this repo's primary checkout | yes | yes | **yes** |
| a real linked worktree | no | yes | no |
| an unrelated repository | yes | no | no |
| a repository whose directory is named `worktrees` | yes | no | no |

`_is_primary` by file-vs-directory rather than by path name is what fixes the
last row, which the draft got wrong in the other direction. Submodules fall out
correctly twice over: their `.git` is a file, and their common dir is
`<super>/.git/modules/<name>`, so neither condition holds — which preserves the
decision `.factory/206/spec-review.md` recorded, that submodule source escapes
this gate.

**When identity cannot be established it fails open.** No session, a session
outside any repository, or an unresolvable `gitdir:` pointer all mean
indifferent. Stated rather than inferred: a gate that cannot tell whose
repository a file belongs to must not invent an answer, and refusing would
break writing to any other project.

## The refusal comes first

| | Condition | Verdict |
| --- | --- | --- |
| **1** | **target in this repo's primary checkout, not exempt** | **refused** |
| 2 | target's worktree on a ticket branch | judged against that chain |
| 3 | session on a ticket branch, target inside this repository | judged against the session's chain |
| 4 | otherwise | indifferent |

The draft had the refusal at row 2, behind the target's ticket. **The primary
checkout can itself be on a ticket branch**, so that left the gate open to
exactly what it exists to stop: create `issue/999-x` in the primary (`git
checkout -b`, through the shell, ungated), write the three artifacts (exempt,
so allowed), and source writes are permitted again. Three permitted writes and
one permitted command.

That is not an exotic state. An agent told "all work happens on an
`issue/<n>-*` branch" which creates the branch and **forgets the worktree**
lands exactly there — the precise mistake this gate exists to catch.

So no branch is consulted at all for a primary-checkout target, which is also
why it cannot be gamed.

### This is a policy fork, not only a bug fix

Row 1 means a human who checks out a ticket branch **in the primary checkout**
and works there, with a complete and reviewed chain, is refused. Flagged to the
maintainer rather than decided quietly, because it is the one place this ticket
goes beyond "block the orchestrator's seat":

- **For it:** the orchestrator's seat *is* the primary checkout, and the bypass
  above is how an agent routes around the intent while technically complying.
  "Work in a worktree" is already the documented rule; enforcing it costs one
  command. The simpler rule is the one that cannot be gamed.
- **Against it:** if the chain is complete, the *sequence* has been honoured;
  what remains is write isolation, which only matters with parallel agents.
- **Reverting it** is one constant, and `FACTORY_HOOKS=off` is the escape
  meanwhile.

Recommendation: keep it. The attack is cheap and the cost is one command.

## The exemptions are their own constant

`_always_writable` matches `relative.parts[0]` against a flat tuple. That shape
cannot express "`configs/**` except `configs/maps/**`", and the draft asserted
the carve-out without saying how.

It also must not be the mechanism, for a reason worth stating plainly: the
obvious shortcut is to append `configs`, `profiles` and `toolkit` to
`_ALWAYS_WRITABLE_ROOTS` — **which is shared with the #206 gate**, so a write
to `<ticket worktree>/toolkit/x.py` with no `spec.md` would become allowed, and
the artifacts-before-code gate would silently lose three top-level trees. No
existing test catches that, because `test_source_is_still_inside_the_gate`
parametrises only `botting/`, `tests/` and `factory/`.

So: a separate constant, prefix-matched, with an explicit deny list.

    PRIMARY_EXEMPT     = (("configs",), ("profiles",), ("toolkit",))
    PRIMARY_REFUSED    = (("configs", "maps"),)
    PRIMARY_EXEMPT_FILES = (".claude/settings.local.json",)

Deny wins over exempt. The universal exemptions (`.factory/**`, `docs/**`,
`AGENTS.md`, `CLAUDE.md`) continue to apply everywhere and are untouched.

**An exempt primary path is indifferent, short-circuiting.** The draft's row
condition was "primary and not exempt", which let an exempt path fall through
to the session row — where `_always_writable(session_root, <primary>/configs/
foo.toml)` raises `ValueError`, returns `False`, and the file is refused for
want of some other ticket's `spec.md`. Exempt means allowed, not merely
not-refused-by-this-row.

### `.claude/settings.local.json`, by name

`OVERRIDE` tells the reader to add `FACTORY_HOOKS: off` to
`.claude/settings.local.json`. Without this exemption the gate refuses the
write its own reason instructs — #189's deadlock, in the seat where it bites
the maintainer.

**Not `.claude/**`.** That directory holds the hooks and the permissions
themselves; #202 removed it from the merge policy's allowlist precisely because
an agent that can edit it can disable the gates. One gitignored, machine-local
file is exempt; the gates are not editable.

### What is refused, enumerated honestly

The draft's "Refused: everything not named below" read as a complete reading of
the tree and covered about half of it. The real top level, minus the exemptions
above:

`botting/`, `maple/` (launchers included), `factory/`, `tests/`, `scripts/`,
`ml_training/`, `research/`, `models/`, `.claude/` (bar the one file),
`.github/`, `.vscode/`, `conftest.py`, `paths.py`, `pyproject.toml`,
`pytest.ini`, `requirements.txt`, `requirements-dev.txt`,
`models.manifest.json`, `.gitignore`, `.pre-commit-config.yaml`,
`.secrets.baseline`, `README.md`, `CONTRIBUTING.md`, `CONTEXT.md`.

`CONTEXT.md` and `README.md` are refused deliberately although they read like
documentation: the glossary is what every agent's vocabulary is checked
against, and changing it is work that belongs in a ticket. `docs/**` remains
exempt because #189 established that a gate must not forbid writing the
document describing its own escape hatch.

### `maple/launchers/**` is not exempt, `toolkit/**` is

A launcher imports the engine and can change what reaches the game. The
*configuration* it reads — `configs/`, `profiles/` — is what the maintainer
asked to keep writable.

`toolkit/**` is exempt because it is run by hand and nothing in the engine
depends on it at runtime. **Not** because "nothing imports it", which the
review found is false: `maple/model/mechanics/minimap_creation/map_editor.py`
imports `toolkit.movement_timeline`, and `toolkit/create_map.py` is the
documented entry point to that editor.

That has a consequence the maintainer should see, since `toolkit/**` was their
call: **the program that writes map JSON is editable in the primary checkout
while the map JSON it writes is refused.** An agent cannot fix a `scale_x` by
hand there, but can edit the tool that produces it.

### `configs/maps/**` blocks the hand-edit path only

Map JSON is on the hard-stop list: recorded data movement depends on, and among
the few things no offline test can check. The draft called the carve-out free
because maps are authored through the GUI editor, a running Python program
writing files directly, which the write gate never sees. **That half is true
and verified.** The other half is not: `Bash`, `python -c` and
`toolkit/create_map.py` all remain open (#207), so this blocks the honest
`Edit` path and nothing else. A speed bump, named as one.

## The #206 correction, verified

#206's session row fires for **any** target, including one under no git
worktree. `_judge` then calls `_always_writable(session_root, target)`, which
raises `ValueError` for an out-of-repo path and returns `False`, so the chain is
consulted — and a write to a **scratchpad or temp file** is refused whenever the
session's chain is incomplete.

Confirmed by running the merged code, twice and independently:

    decide_write(<temp>/scratch/notes.md, session=<ticket worktree, no spec>)
    -> allowed = False, "Ticket 50 has no .factory/50/spec.md"

It contradicts #206's own principle, which this spec keeps: *the factory
governs this repository, not the filesystem.* Row 3 therefore requires the
target to be **inside this repository** — by the same `_common` identity as row
1, which is the definition the draft left to three disagreeing readings.

Note the fix is narrower than the principle: a scratch directory that happens
to sit inside *some other* git repository is now indifferent (good), but
`governing()` returns non-`None` for a detached-`HEAD` worktree, so a scratch
path inside **this** repository still reaches row 3. "Under no worktree" is not
"outside this repository", and the identity test is what closes the gap.

## One edit to revert, and a test that proves it

The maintainer is trying this provisionally, so reverting must be **one edit**.
The draft also promised "one test goes red", which is false — at least eight
would, since most criteria here test the rule. Promising one and delivering
eight is a promise that breaks at the worst moment, so: **one edit, and the
tests named by criteria 1-9 go red.**

The draft's criterion for single-sourcing pinned syntax and was satisfiable by
a copy-pasted literal. Replaced with the review's version, which tests
*control* rather than *references*:

> Force the single predicate off (`monkeypatch.setattr` on `_is_primary`), then
> assert no input in the primary-checkout case set produces a refusal, and that
> every other gate test still passes.

That survives refactors, and it is the revert rehearsal. It also resolves the
contradiction with the awareness criterion: the `SessionStart` line may reuse
the same constant freely, because the property is single-source control, not a
reference count.

## Awareness: four places, and the wrong one fixed

Nassim: *"ALL agents need to be aware of this mechanism, I don't want a random
agent to 'have to figure this out on its own'."*

1. **`OFF_TICKET` is rewritten, not appended to.** It currently says the gates
   apply to files *in a worktree*, which in the primary checkout now reads as
   "files here are free" — the opposite of the new rule. A line beside a
   contradictory sentence is worse than no line.
2. **Both report paths carry it.** `session_report` returns early for a
   non-ticket branch; the ticket-branch path needs the line too, precisely
   because row 1 makes primary-on-a-ticket-branch a real and refused state.
3. **The report resolves its root the way the gate does.** It currently uses
   `Path.cwd()` verbatim while the gate walks up, so a session whose cwd is a
   subdirectory (`<primary>/maple`) gets **no line while its writes are
   refused** — the exact "figure it out by being denied" failure. It resolves
   through `governing()`.
4. **`AGENTS.md`, `stages.md`, `README.md`'s marker table, and the `factory`
   skill.** The draft dropped the last two. Its reason for dropping the skill
   was wrong twice: the primary checkout can be on a ticket branch, and the
   skill triggers on being *asked to pick up a ticket*, which is an
   orchestrator in the primary — the seat this ticket is about.

Plus the deny reason, self-contained: what is refused, what is exempt, and what
to do instead.

## The way forward, and where the artifacts go

`factory claim` (#147) does not exist, so the refusal names what works today:

    git worktree add ../<slug> -b issue/<n>-<slug>

reading the **current** branch for the base rather than naming one.

And it must say **write the artifacts in the new worktree**. `.factory/**`
stays writable in the primary — refusing it is #189's deadlock — but `git
worktree add -b` carries no uncommitted changes, so artifacts written in the
primary orphan there, the new worktree's chain is empty, source is refused in
it, and `_source_changed` filters `.factory/` so the Stop gate never mentions
them. A silent dead end the reason can prevent in one clause.

## Tests that change meaning

Named, per the house rule that a `method: suite` spec which does not name the
suite it breaks has not costed itself. The identity requirement rescues three
of the four the review predicted, because each `tmp_path` fixture is its own
repository:

| Test | After |
| --- | --- |
| `test_ordinary_branches_are_never_blocked` | green — no session, so identity fails open |
| `test_a_ticket_session_writing_to_the_trunk_is_still_judged` | green — different repositories, so row 3 still answers |
| `test_the_pre_tool_use_hook_passes_the_session_so_row_two_survives` | green — same reason |
| `test_neither_side_a_ticket_is_indifferent` | **inverts** — its fixture is exactly the case now refused |

The last is rewritten to assert refusal, with a docstring saying why rather
than being quietly adjusted. **The suite is the arbiter, not this table:** it
is reasoning about code that does not exist yet, and the PR body will report
what actually happened.

The session row keeps a regression detector, since almost nothing reaches row 3
once row 1 exists: a **linked, non-ticket** worktree target, which the identity
rule leaves reaching it.

A genuine linked-worktree fixture is also needed — a real `gitdir:` pointer,
not a `.git` directory — because no existing fixture is one, and criterion 2
cannot be tested without it.

## What cannot be verified before merge

`-m factory` loads code from the process cwd, so a session rooted in the
primary runs **the primary's** `hooks.py`. This gate is inert in its own
worktree until merged, and `test_hook_wiring.py` passes `cwd=ROOT`, so the
suite cannot see the divergence either. That bites harder here than in #206,
because the subject of this gate *is* the primary checkout: the maintainer's
first live experience of it is after merge, in their own seat.

## What this does not do

- Does not add roles. #163 sits on this floor.
- Does not catch a write through the shell (#207), and makes that hole matter
  more, since the primary checkout is where a shell is handiest.
- Does not enforce the hard-stop list generally; `configs/maps/**` is refused
  here as a consequence of this rule, not as hard-stop enforcement.
- Does not exempt `configs/`, `profiles/` or `toolkit/` **inside** ticket
  worktrees. Whether the maintainer wants that is unanswered by `intent.md`;
  this spec says no, so the artifacts-before-code gate keeps every tree it has.
- Does not stop the maintainer. `FACTORY_HOOKS=off` is the escape, and this is
  a floor rather than a lock.

## Radius

Named in `plan.md`, not here.
