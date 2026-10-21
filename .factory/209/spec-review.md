---
ticket: 209
stage: design
verdict: changes-requested
reviewed_by: claude (read-only reviewer, stand-in for #180)
reviewed_at: 2026-10-18
criterion_quoted: "a source write in the primary checkout is refused, whatever branch it is on and whatever the session is"
---

# Spec review: refuse source writes in the primary checkout

**Verdict: `changes-requested`.** Eleven findings. The reviewer's summary is
accurate and worth quoting, because it names three separate ways the draft
would have failed:

> As written a Builder would ship a gate that the thing it exists to stop walks
> straight through, a predicate that fires on every git repo on the machine,
> and a red suite the spec never costs.

Two of the draft's load-bearing claims were verified by running the current
code and **both check out**: the #206 over-reach is real, and the row-ordering
argument is true. The draft was wrong about almost everything else.

## The two that broke the design

### 1. The gate was open to exactly the thing it exists to stop

The draft kept row 1 (the target's ticket) ahead of the refusal, reasoning that
a path inside a ticket worktree is governed by that ticket. **But the primary
checkout can itself be on a ticket branch.** The reviewer walked it:

> `git checkout -b issue/999-x` (Bash - ungated), then write
> `.factory/999/intent.md`, `spec.md`, `spec-review.md` (all exempt, so all
> allowed in the primary). Now `decide_write(<primary>/botting/controller/
> inputs/focus.py)` -> `allowed=True`. The motivating example from `intent.md`
> is reachable again after three permitted writes and one permitted shell
> command.

And it is not an exotic state: *"an agent told 'all work happens on an
`issue/<n>-*` branch' that creates the branch and forgets the worktree lands
exactly here - the precise mistake this gate exists to catch, and the one case
where it says nothing."*

The draft also asserted the opposite in prose - "not a Builder with a perfect
chain" - and in criterion 2, "whatever branch it is on". It could not keep both.

**Decided: the refusal moves to row 1, ahead of everything.** No branch is
inspected for a primary-checkout target at all, which is also why it cannot be
gamed. This is a **policy fork rather than a pure bug fix**, and it is flagged
to the maintainer in the PR body: it means a human who checks out a ticket
branch in the primary checkout and works there, without a worktree, is refused
even with a complete chain.

### 2. `is_primary` fired on every git repository on the machine

The draft handed over the implementation verbatim, so a Builder would not have
improved on it:

    return found is not None and found.parent.name != "worktrees"

Nothing tied `found` to *this* repository. The reviewer's first case is the
expensive one:

> `decide_write(C:/Users/Nassim/code/OtherProject/main.py, session=<anywhere>)`
> -> `is_primary` **True** -> **refused**, with a reason telling the agent to
> `git worktree add` in the Legends factory. #206 exists precisely because
> agents write other checkouts by absolute path, so this is reachable.

Plus: every `tmp_path` fixture in the suite became "the primary checkout"
(causing finding 3); a submodule's git dir resolves under `modules/`, so
submodule source became primary-checkout source, **silently inverting a
decision `.factory/206/spec-review.md` had recorded**; and it read `False` -
gate silently off - for a repo whose own directory is named `worktrees`, or a
`--separate-git-dir` repo whose git dir sits under one.

I had found the last of those independently before the review returned. I had
not found the first, which is the one that matters.

**Decided:** the test needs **identity, not shape**. Two parts:

    (root / ".git").is_dir()                 # a linked worktree's .git is a FILE
    common(target_root) == common(session_root)   # the same repository

where `common` is the computation `factory/cli.py` already performs
(`gd.parent.parent if gd.parent.name == "worktrees" else gd`). Verified against
four real roots: this repo's primary -> refuse; a real linked worktree -> no; an
unrelated repo -> no; a repo named `worktrees` -> no. Submodules fall out
correctly twice over, since their `.git` is a file *and* their common dir
differs.

When identity cannot be established - no session, or a session outside any
repository - it **fails open**, which the spec now states rather than leaving
to be inferred.

## Acted on, as specified

### 3. Four pinned tests invert, and the spec named none

The house rule is `.factory/206/spec-review.md`'s: *"a `method: suite` spec
that does not name the suite it breaks has not costed itself."* The draft's
"what this does not do" listed four things, none of them this.

The reviewer's sharpest point here was not the count but which detector dies:
`test_the_pre_tool_use_hook_passes_the_session_so_row_two_survives` exists so
that dropping `session=` is noticed, and after the reordering *almost no input
reaches the session row any more*, so it stops detecting that.

> The spec reorders rows in a way that removes the regression detector for the
> row it says must be preserved, and does not say so.

**Decided:** the identity fix rescues three of the four by itself - each
`tmp_path` fixture is its own repository, so cross-fixture writes are no longer
"same repo" and still reach the session row. One genuinely inverts,
`test_neither_side_a_ticket_is_indifferent`, and it inverts *because its fixture
is exactly the case now refused*; it is rewritten to assert refusal with a
docstring saying why. The session row keeps a detector, now a linked
**non-ticket** worktree target, which the identity rule leaves reaching row 3.
The spec names all of this, and the suite is the arbiter rather than my
analysis.

### 4. The exemption list could not be expressed, and the obvious shortcut loosens #206

`_always_writable` matches `relative.parts[0]` against a flat tuple, so
`configs/**` except `configs/maps/**` does not fit its shape at all - and the
draft asserted the carve-out without saying how. I had found this much myself.

The reviewer found the worse half:

> The shortcut a Builder will reach for first: appending `"configs"`,
> `"profiles"`, `"toolkit"` to `_ALWAYS_WRITABLE_ROOTS`. That constant is
> **shared with the #206 gate**, so `decide_write(<ticket worktree>/toolkit/
> x.py)` with no `spec.md` becomes **allowed** - the artifacts-before-code gate
> loses three top-level trees inside ticket worktrees. No existing test catches
> it.

**Decided:** a **separate** constant, prefix matching with an explicit deny
list, and a criterion asserting the new exemptions do **not** apply inside a
ticket worktree. Also settled, because the draft left it ambiguous: an exempt
primary path is **indifferent**, short-circuiting, rather than falling through
to the session row - otherwise `<primary>/configs/foo.toml` is refused for want
of a `spec.md` belonging to some other ticket.

### 5. The gate refused the write its own escape hatch instructs

`OVERRIDE` tells the agent and the maintainer to add `FACTORY_HOOKS: off` to
`.claude/settings.local.json`. `.claude` was not exempt, and the draft said
"Refused: **everything** not named below".

> So in the primary checkout - the one checkout a human actually sits in -
> `Edit(<primary>/.claude/settings.local.json)` is **refused by the gate whose
> reason just told you to write it.**

That is #189's deadlock through a new door, in the place it bites the
maintainer rather than an agent.

**Decided:** `.claude/settings.local.json` is exempt **by name**, not
`.claude/**`. The directory holds the hooks and permissions themselves, and
#202 removed it from the merge policy's allowlist precisely because an agent
that can edit it can disable the gates. Exempting the one gitignored,
machine-local file makes the escape hatch reachable without making the gates
editable.

The reviewer also demolished the draft's "Refused:" list as a reading of the
tree - it looked complete and covered about half of a 20-entry root. The spec
now enumerates the real top level, and the omissions it found are refused
deliberately and said so.

### 6. "One constant, one call site" was unachievable and its test was fake

Three separate problems, all correct:

- It contradicted criterion 10: if "one call site" means one reference, the
  `SessionStart` line cannot reuse the constant, so the rule text must be
  duplicated and drift.
- *"One test going red" on revert is false by the spec's own criteria* - at
  least eight would. The maintainer's constraint is one **edit**, and promising
  one test is a promise that breaks at the worst moment.
- Criterion 7 was not testable: every cheap version pins *syntax* and is
  satisfied by a copy-pasted literal at a second site.

The reviewer supplied the honest version, which is better than anything I had:

> **A monkeypatch test.** Force the single predicate off, then assert that no
> input in the primary-checkout case set produces a refusal, and that every
> other gate test still passes. That proves single-source *control* rather than
> single *reference*, survives refactors, and is also the revert rehearsal.

**Decided:** adopted as the criterion. "One edit" stays as the promise; the
number of tests that go red is named rather than minimised.

### 7. The awareness requirement was not met by the draft's three places

Nassim's constraint is an acceptance criterion, not a nicety, and the draft
failed it four ways:

- **`OFF_TICKET` becomes actively misleading.** It says the gates apply to
  files *in a worktree*, which now reads as "files here are free" - the
  opposite of the new rule. The draft asked for a line *beside* it, and
  criterion 10's substring assertion would have passed with the contradictory
  sentence still in place. #206's review set the precedent: the wrong doc gets
  fixed, not preserved.
- **The ticket-branch path of `session_report` got no line**, which matters
  precisely because finding 1 makes primary-on-a-ticket-branch real.
- **The report's root and the gate's root were computed differently.** The
  report uses `Path.cwd()` verbatim; the gate walks up. A session whose cwd is
  a subdirectory gets **no awareness line while its writes are still refused**
  - the exact "figure it out by being denied" failure.
- **Two accepted acceptance items were dropped**: the `factory` skill and
  `README.md`'s `[mechanical]` marker. My reason for dropping the skill was
  wrong twice - the primary checkout can be on a ticket branch, and the skill
  triggers on being *asked to pick up a ticket*, which is the orchestrator in
  the primary, the seat this ticket is about.

**Decided:** all four. `OFF_TICKET` is rewritten rather than appended to; both
report paths carry the line; the report resolves its root through `governing()`
like the gate; the skill and the marker table are back as criteria.

### 8. The `toolkit/` justification was factually false

The draft said "imported by nothing". The reviewer found that
`maple/model/mechanics/minimap_creation/map_editor.py` imports
`toolkit.movement_timeline`, and that `toolkit/create_map.py` is the documented
entry point to that editor and writes `configs/maps/*.json`.

Which turns the carve-out's own argument around:

> The exemption two rows above the carve-out makes **the map-production program
> freely editable in the primary checkout, while its output is refused**. An
> agent in the primary cannot fix a `scale_x` by hand but can rewrite the tool
> that writes it.

And it halves the "costs nothing" claim: map *authoring* is genuinely untouched
because the GUI writes through a Python process no hook sees, but *"the honest
`Edit` path is the only one blocked - Bash, `python -c` and
`toolkit/create_map.py` all remain open (#207) - so the carve-out is a speed
bump sold as a free decision."*

**Decided:** the justification corrected, "costs nothing" downgraded to "blocks
the hand-edit path only", and the tension surfaced to the maintainer rather
than buried, since `toolkit/**` being exempt was their call.

### 9-11. Three smaller ones, all taken

- **"Inside the repository" was undefined**, with three readings that disagree.
  Now defined by the same identity computation finding 2 needs, stated once.
- **The gate cannot be observed working before merge** - `-m factory` loads
  code from the process cwd, so the primary runs the primary's `hooks.py`.
  #206 carried this; #209 had dropped it. Back in the spec and the PR body, and
  it bites harder here because the subject of the gate *is* the primary.
- **Artifacts written in the primary stay behind.** `.factory/**` must stay
  writable there or it is #189 again, but `git worktree add -b` carries no
  uncommitted changes, so the artifacts orphan - and `_source_changed` filters
  `.factory/`, so the Stop gate never mentions them. The deny reason now says
  *write the artifacts in the new worktree*.

The reviewer also walked the whole primary-checkout flow and confirmed it is
satisfiable - nothing an agent must do first is refused - which is the one
thing I most wanted checked and could not check myself.

## Criteria, after the rewrite

Of the original ten the reviewer judged: 2 unsatisfiable, 6 not decidable, 7
not testable, 1 and 5 self-satisfying, 3 and 9 session-dependent or
unverifiable, 10 partial. Only criterion 8 survived intact - *"the best
criterion in the list"*, and the only one confirmed red today.

All rewritten. The additions are the ones the gaps demanded: that the new
exemptions do not apply inside ticket worktrees, that identity is required, the
monkeypatch control test, and that `OFF_TICKET`'s contradictory sentence is
gone rather than merely joined.

## What the review could not check

- The test inversions are by inspection; the code did not exist yet. The suite
  arbitrates, and the spec says so.
- A live harness invocation: whether `SessionStart`'s cwd is ever a
  subdirectory, and whether this version's payload carries `cwd`. Both
  inherited from #206.
- The installed git's `worktree.useRelativePaths` (git >= 2.48), which can
  change the `gitdir:` pointer's shape.
- A bare-repo-plus-worktrees layout, which `governing()` never finds at all.
- Whether the maintainer wants `configs/`, `profiles/` and `toolkit/` exempt
  **inside ticket worktrees** too. `intent.md` does not answer it; this spec
  says no, and flags it.
