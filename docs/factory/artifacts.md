# The artifact chain

One directory per ticket, on the ticket's branch. Each file is markdown a person
reads, carrying YAML front-matter a program reads — so the stage can be computed
from the artifacts themselves rather than from a separate state file.

```
.factory/133/
  intent.md     # what is wanted, why, under which constraints
  spec.md       # requirements, criteria, and the verification method
  spec-review.md # a verdict on the spec, by someone who did not write it
  plan.md       # tasks, files changing, order, the radius, proof of completion
  tasks/        # per-task records, when the plan declares tasks
  qa.md         # the Run Report -- only when spec.md says the method is live
  review.md     # findings against docs/factory/review-policy.md
```

It lives on the branch, not in the issue body, for three reasons: the chain
travels with the PR so a reviewer sees intent, spec, plan and evidence in one
diff; hooks read it with no network call; and an edit to the criteria after the
fact shows up in `git log` as what it is. The GitHub issue stays the
human-facing surface and references the commits.

## Front-matter contracts

A parser implements these; `factory spec check` and friends enforce them.
Required fields are required — a missing one is an error naming the field, not a
default.

### `intent.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | The issue number. Must match the directory. |
| `stage` | `plan` | Always `plan`; intent is stage 1's artifact. |
| `accepted_by` | string \| null | Who accepted it. `null` until accepted. |
| `accepted_at` | date \| null | When. |

Body sections, all required, empty ones marked rather than omitted: problem
statement, proposed outcome, affected users and systems, constraints, open
questions.

### `spec.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | Must match the directory. |
| `stage` | `design` | |
| `method` | `suite` \| `live` \| `both` \| `assent` | **What settles it.** The field the whole factory turns on. |
| `criteria` | list of strings | Each one decidable. See below. |
| `specified_by` | string | Who wrote the criteria. |
| `specified_at` | date | |
| `reviewed_by` | string \| null | The Specification Reviewer's verdict. `null` blocks stage 3. |

**`spec.md` does not carry the radius.** That lives in `plan.md`. The radius is
an implementation fact nobody knows until the code has been read, and if it
lived here the Builder would eventually need to edit this file — and a Builder
that can write to `spec.md` at all can soften the criterion it is judged against.

**A criterion must be decidable.** Could two honest people disagree about
whether it was met? Then it is not a criterion yet. "Works correctly" fails;
"`pytest -m lab` reports 23 selected" passes.

**For `method: live`**, the criteria must additionally name the schedule, the
metric and the number — all fixed *before* any run. An agent handed both the
data and the authority to pick the bar will fit one to the other, honestly and
unconsciously.

### `spec-review.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | Must match the directory. |
| `verdict` | `pass` \| `changes-requested` | |
| `reviewed_by` | string | Who reviewed. Never the same as `spec.md`'s `specified_by`. |
| `reviewed_at` | date | |

The body must **quote at least one criterion and judge it**. That requirement is
the whole mechanism: a verdict is a file someone had to write, not a boolean in
`spec.md` that the Builder also owns.

**What this does and does not buy.** It cannot prove a different agent reviewed
the spec. It makes forging one cost about what doing it costs — to write a
review that quotes criteria and judges them, you have to read the spec against
the intent, which is the review. Ordering is checkable too: the review commit
touches only `.factory/<n>/` and lands before any source commit.

Only #163 makes this structural, by spawning the reviewer so the Builder never
has the chance. Until then this shapes cost rather than preventing.

### `plan.md`

| Field | Type | Meaning |
| --- | --- | --- |
| `ticket` | int | |
| `stage` | `build` | |
| `radius` | list of globs | **The only paths Build may touch.** |
| `tasks` | list \| null | Each with `id`, `radius`, and `parallel`: true/false. |
| `merge_order` | list \| null | Required when any task is parallel. |
| `proof` | object | `red_test`, `red_output_sha`, `suite` — filled at stage 5. |
| `docs_cleared` | list \| null | Coupled documents needing no change, each with a reason. `[]` when stage 8 ran and every coupled document was updated; `null` until stage 8 has run. |

### `qa.md` and `review.md`

`qa.md` is written only when `method` is `live` or `both`. It must name the
schedule, the **commit** it ran against, the number of trials, the measured rate
against the criterion, and the defects counted. **A Run Report that does not name
a commit is not evidence — it is a story about a different build.**

### Verdicts: `review.md` and `qa.md`

Both carry a `verdict`, and it is one of exactly three values:

| `verdict` | Means | What `factory next` does |
| --- | --- | --- |
| `pass` | The stage is satisfied | Moves on |
| `changes-requested` | Fixable; the Builder has work | Routes **back to Build** |
| `fail` | Not fixable from here | Stops, exit 3 |

Three rules follow, and each exists because the alternative was tried:

- **A missing or `null` verdict is an unfinished artifact, not a rejection.** It
  routes back to that stage so the review can be completed. Treating absence as
  failure wedged tickets at exit 3 on a review nobody had finished.
- **An unrecognised value is an error**, never guessed. Guessing `pass` merges
  unreviewed work; guessing `fail` wedges the ticket. Both silently decide
  something a person wrote a word about.
- **`changes-requested` is not a dead end.** The routing table once had only
  "stop and hand back" here, which made every rejected review a manual rescue.

### `model`: reserved, not yet placed

A stage artifact may carry a `model` field recording which model produced it,
so a bad result traces back to the model that produced it rather than to a
guess. `factory model` (#162) emits the line in a contracted shape:

    model: <alias>  # tier=<tier>, rule=<rule>

**No artifact is required to carry it yet, and nothing writes it today.** Four
of the nine stages that get a model have nowhere to put one: stage 4's artifact
is the diff, stage 5 has no artifact, and `review.md` and `qa.md` have no
contracted front matter until #152. The field name is reserved here so that
when the Foreman (#159) starts recording it, there is one spelling rather than
two.

The alias is what the table holds -- `opus`, `sonnet`, `haiku`, `fable` -- not a
concrete model id. Ids churn; the policy is written in tiers and the aliases are
what a harness accepts. See `configs/factory-models.toml`.

## Tickets and tasks

`plan.md` may declare tasks, and several Builders may work them in parallel
worktrees. **Tasks do not get tickets or chains of their own.**

A ticket is the unit of *acceptance*; a task is the unit of *work*. A ticket has
a `spec.md` — criteria and a method, written by someone who is not the Builder.
A task inherits them and cannot be judged done on its own, only finished. Task
records nest under `tasks/` and carry no `criteria` and no `method`.

**If a task needs its own `spec.md`, it is a ticket, and the split happened at
the wrong stage.** Splitting belongs at Design, where criteria are written, not
at Plan, where work is divided. Three signals mean a slice was really a ticket:
it needs a different verification method from its siblings, it touches a
hard-stop path while they do not, or it could merge alone and still be worth
something.

One ticket, one spec, one PR. Parallel worktrees merge into the ticket's own
branch in the order `plan.md` states — never into the trunk independently.
