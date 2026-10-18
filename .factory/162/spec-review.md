---
ticket: 162
stage: design
verdict: changes-requested
reviewed_by: claude (read-only reviewer, stand-in for #180)
reviewed_at: 2026-10-18
criterion_quoted: "the stage vocabulary is imported from factory.routing, not respelled"
---

# Spec review: the model routing table

**Verdict: `changes-requested`.** Not because the reasoning was unsound, but
because a Builder could not have implemented it: the shipped override table
would have made `factory model` exit non-zero for every ticket, and criterion 8
was unsatisfiable against the stage list the spec itself printed.

Twelve findings. The spec was rewritten against them; what follows records what
was wrong and what was decided, so a later reader can see which parts of the
design are *argued* rather than assumed.

## Acted on, as specified

### 1. All three shipped overrides were inert or fatal

The spec made "a fact the resolver cannot evaluate" a hard error and called that
the case that mattered most. Then it shipped three overrides whose facts could
not be evaluated:

- **`touches_hard_stop`** needs the radius, and the radius lives in `plan.md`,
  the *output* of stage 3. The Foreman needs a model for `plan`, `design` and
  `build-planning` **before `plan.md` exists** - the fact is not unknown there,
  it is unknowable. The hard-stop list is also prose in `AGENTS.md`,
  hand-duplicated in `merge.py`, with `merge-policy.md` saying outright that it
  drifts and that #143 owns a machine-readable version.
- **`method = "live"`** is readable, but `spec.md` does not exist during `plan`
  or `design`, so it is empty at the two stages where it would matter most.
- **`escalated`** is set by nobody; the spec admitted as much.

So `factory model 162` on a fresh ticket would have hit the first override, had
no way to evaluate it, and errored. Every call, every ticket. The Builder's only
escapes were to invent a fact source the spec never named, or to let an unknown
key quietly evaluate false - the exact failure the spec called the worst one.

**Decided:** facts are a **closed vocabulary the resolver computes from the
chain**, and the spec now separates two things it had conflated:

| | Means | Answer |
| --- | --- | --- |
| A fact **name** the vocabulary does not hold | the table is wrong | table error, exit 3 |
| A known fact **not yet knowable** at this stage | the chain has not got there | the override does not fire, exit 0, reason says so |

One override ships: `method_live`. `touches_hard_stop` is **not shipped** and
the spec says why - it waits on #143's machine-readable hard-stop list and on a
chain reader that can read a list. Shipping the mechanism with one working
override beats shipping three that cannot fire.

### 2. `spec-review` is not a stage

`routing.Stage` has nine members and no `spec-review`; the Specification
Reviewer is a **role inside stage `design`** (`stages.md:104-110`). The amended
issue body asserted otherwise and the spec copied it. A test asserting the
table's keys against `Stage` would have failed on the shipped table.

**Decided:** `spec-review` dropped. `design` covers both roles and both would
have resolved to `complex` anyway. Recorded in the spec: if Design's two roles
ever need different tiers, that needs a role axis and a ticket, not a tenth key
that looks live and is dead. The spec also now answers the case it had missed -
**the table naming a stage the vocabulary does not have** is a table error - and
says that `maintain`, documented in `stages.md` but absent from `Stage`, is a
caller error to ask for.

### 3. "Every malformed input is MISUSE" contradicted the exit-code contract

`exit_codes.py` defines `MISUSE` as "wrong arguments, or the wrong stage for
this command"; `NEEDS_HUMAN` is "stop, comment on the ticket, hand back". The
spec collapsed five classes into `MISUSE`, and three of them are not argument
errors at all: a missing table, an unparseable table and an undefined tier are
things the *caller did not write*. The house precedent goes the other way -
`cli.py` maps `MalformedVerdict`, the closest analogue, to `NEEDS_HUMAN`.

The consequence named was decisive: the Foreman could not tell "I asked a
nonsense question, skip and carry on" from "the model table is broken, stop
everything and get Nassim", and `MISUSE`'s documented remedy, *re-read `factory
next`*, is useless advice for a corrupt config file.

The review also noticed that the spec's own argument - "a silent fallback to
`opus` turns a typo into a bill" - only supports *not falling back*. Exit 1 and
exit 3 are equally non-fallbacks.

**Decided:** argument errors are `MISUSE` (2); table errors are `NEEDS_HUMAN`
(3). The split is now a table in the spec.

### 4. The one line the maintainer is invited to edit was unvalidated

`unavailable = ["fabel"]` - one transposition - would have resolved `complex` to
`fable`, exit 0, with a confident reason, and the Foreman would spawn a session
against a model that does not exist. The single advertised edit was the one
unguarded input.

**Decided:** every name in `unavailable` must appear in some tier's chain, or it
is a table error. An empty tier is a table error too.

### 5. Fact provenance, comparison semantics and the test seam

Three different sources had been named for facts across the intent, the spec and
a superseded comment - front matter, ticket labels, and nothing. Labels need
`gh`, which breaks "pure and offline".

**Decided and written down:** facts come from the chain, nothing else; labels
are explicitly out of scope *and why*. A multi-key `when` is **AND**. An empty
`when` is a table error. Values are compared after the same stripping
`verdict_of` does, because `chain.py` does not strip quotes and `method: "live"`
would otherwise silently never match. `method_live` covers **both `live` and
`both`**, matching `chain.needs_qa` - otherwise a `method: both` ticket got
`standard` at Review where an identical `live` ticket got `complex`.

The seam question answered itself once facts became chain-derived: a test
fabricates a chain in `tmp_path` and passes a table path. **No caller-supplied
facts**, which also closes a hole the review spotted - an agent that can pass
`escalated = true` has chosen its own model through one indirection.

### 6. Keying the command on a ticket made the Foreman's loop awkward

`factory next` returns exit 0 for `integrate`; the spec made `factory model`
exit 2 for it. The Foreman would have to special-case `integrate` *before*
calling - i.e. already know the thing the resolver refused to tell it. Two
further `resolve` outcomes were unspecified: a blocked chain, and a non-ticket
branch.

**Decided:** `integrate` answers `model: null` at **exit 0**, with a reason
naming CI. A definite "nobody runs this" is an answer, not a refusal. Added
`--stage` so the command can be asked directly, with the ticket form as a
convenience; a blocked chain exits 3 and carries `blocked_by` through; no ticket
and no `--stage` is `MISUSE`.

### 7. Nothing stopped an override routing *down*

The spec stated the one-direction rule as an invariant and enforced nothing.
`use = "trivial"` names a defined tier and passed every listed check, so a live
ticket's Review could run on Haiku at exit 0 with a reason that proudly named
the rule.

**Decided:** tiers are ordered, and an override naming a tier not strictly above
the stage's is a table error.

### 8. The file was in the wrong place

A `.toml` inside the package is not installed - `pyproject.toml` has no
`package-data` - so on a non-editable install every call would fail. Fixing that
means editing `pyproject.toml`, which is a **hard-stop path**, so the ticket as
specified would have stalled at stage 3 for scope approval. And `intent.md`
wanted the maintainer to change policy "without a code change", which a file
inside an installed package is not.

**Decided:** the table lives at **`configs/factory-models.toml`**, resolved from
the repo root like every other chain read. No packaging question, no hard-stop
edit, and it sits where this repo already keeps settings a human edits. A side
effect worth having: `configs/` is not in the merge policy's `allowed_paths`, so
a change to the model table can never auto-merge.

### 9. Criterion 9 named the wrong file

`test_merge.py` computes the console script's transitive import closure and
fails when a module joins it unlisted. The moment `cli.py` imports
`factory/models.py`, that test goes red until **`models.py`** is in
`protected_paths` - and the criterion asked for `models.toml`, which no test
demands. The Builder would have met the criterion and still had a red suite.

The review also objected to protecting the `.toml` at all: `protected_paths`
means "the policy, or anything its verdict depends on", and the merge verdict
does not depend on the model table. Widening that set's meaning needed an
argument the spec did not make.

**Decided:** `factory/models.py` goes in `protected_paths` and in
`merge-policy.md`, because the closure test demands it. The `.toml` does not,
and needs no protection: `configs/` cannot auto-merge anyway.

### 10. "`artifacts.md` names the front-matter field" - which artifact?

Four of the nine stages that get a model have nowhere to record it: stage 4's
artifact is *the diff*, stage 5 has no artifact, and `review.md` and `qa.md`
have no contracted front matter until #152. The spec asserted a field on files
that do not exist.

**Decided:** this ticket contracts the **shape** of the record line and reserves
the field name in `artifacts.md`, so nobody invents a second spelling. Where it
lands is #159's, when there is a Foreman to write it. Said plainly in "what this
does not do" rather than implied.

### 11. Requirements that went missing in the amendment

The amendment traded away the body's **default** without acknowledging it: the
body still read "`standard` - the default. Most stages", while the rewritten
spec enumerated every stage and made anything else an error. The review's
argument for restoring it is the one I had over-generalised: the spec's own case
is against silent *escalation*, and `standard` can never silently spend on the
strong model, so halting the Foreman over a stage the table forgot is the worse
failure.

**Decided:** a stage **in the vocabulary** but absent from the table resolves to
`standard` at exit 0, with a reason naming the default. A stage **outside** the
vocabulary is still a caller error. Two other dropped items are now acknowledged
rather than silently gone: `type:grilling` is a label and unreachable offline,
and *runtime* availability failure - a worker that could not get Fable - is
#159's, not this resolver's.

### 12. The record line had no shape

#159 would have had to invent it twice. Now contracted.

## Not acted on

Nothing. All twelve were acted on in the spec rewrite; findings 1, 2, 3, 8 and
11 changed the design rather than its wording.

## What the review could not check

- Whether any model alias is real. `intent.md` already admits this ticket
  cannot prove it.
- Whether `factory` is installed editable here. It is, which is precisely why
  finding 8 was invisible: an editable install hides the missing `package-data`
  completely, and a fresh `pip install .` would have exposed it.
- The pre-amendment issue body, which `gh` no longer serves; the review read the
  amendment against the comments describing it.

## What the review found outside its own ticket

Reading `chain.py` to check whether the override facts were readable at all, the
reviewer found that `front_matter` skipped every indented line while
`artifacts.md` contracts `plan.md`'s `proof` as an object. `has_proof` was
therefore **false for every real ticket**: `factory next` could never leave
`build-implementing`, and the `Stop` hook would have refused to let any ticket
finish. The suite was green because all three fixtures wrote a top-level
`suite:` in a shape no artifact has.

Fixed in #140, which was still open - `c3e69c3`, 13 tests red without it. This
ticket's branch is rebased on it.
