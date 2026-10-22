# The factory

A fixed sequence of stages, each defined tightly enough that an agent
performing one has little room to improvise. Randomness is the enemy: two
agents handed the same ticket should produce the same shape of work.

**If you are on an `issue/<n>-*` branch, you are working a ticket in the
factory.** Read this page, then [stages.md](stages.md) for the stage you are
in. The artifacts come before the code.

## The one rule everything else follows from

**A stage is done when it has produced its artifact, and the next stage refuses
to start without it.** Not when an agent says it is done. The artifact is what
removes the randomness — an agent cannot talk its way past a missing file.

## How to read the enforcement markers

This documents a process that is largely not built yet. Every rule below carries
one of three markers, and they are not interchangeable:

| Marker | Means |
| --- | --- |
| **[mechanical]** | A command or hook refuses. You cannot proceed by deciding to. |
| **[instruction]** | Written down, and nothing checks it. Honoured because you choose to. |
| **[unenforced]** | Stated as intent. Not written down anywhere a tool could read, and not checked. |

**What is [mechanical] today**, so the list can be checked rather than
believed: artifacts before code and the spec-review gate (`PreToolUse`, #189);
the proof before a turn ends, across every ticket worktree (`Stop`, #206); the
stage a ticket is in (`factory next`, #140); the auto-merge conditions
(CI, #194); and source edits in the primary checkout being refused (#209).
Everything else in this directory is **[instruction]** or **[unenforced]**, and
labelled.

A rule that is **[instruction]** today is a ticket waiting to make it
**[mechanical]**. If you find yourself relying on an **[instruction]** rule and
it would have mattered, say so on the ticket — that is the signal that it has
earned being built.

## Decide and record

**When the answer is not in the repo, and is not one of the three things below,
decide it yourself.** Choose the conservative option, write the choice and your
reasoning into the artifact under a "Decisions I made" heading, and continue.

**Do not stop to ask what you could defensibly decide.** A decision recorded and
wrong is cheap — it is visible in a diff and reversible in a comment. A ticket
that produced nothing is not.

Exactly four things need the maintainer:

1. **Scope approval** on a hard-stop path in `AGENTS.md`
2. **Risk and trust appetite** — what may merge unreviewed, how much supervision
3. **Product priority** — what matters, what can wait
4. **Observation** — anything that reduces to watching the character on a
   running client: a measured constant, a minimap trail, a timing or animation
   number, "does the rotation look right"

Anything else is yours. If one of those four really is in the way, it goes in
the **PR body**, under "Decisions you may want to reverse" — batched, with what
you chose and why. Never asked mid-session: one review beats ten interruptions.

Item 4 is in the list, not in a footnote, deliberately. An earlier draft of this
page named only the first three and added the observation class as a closing
assurance — which meant an agent applying the stated test ("is it one of the
three? no → decide") would correctly plough straight through a measured
constant. The review caught it before it shipped. **[instruction]**

## The stages

| # | Stage | Artifact | Gate to leave it |
| --- | --- | --- | --- |
| 1 | Plan | `intent.md` | Accepted by the maintainer |
| 2 | Design | `spec.md` | Criteria and `method` both explicit; a reviewer verdict exists |
| 3 | Build, planning | `plan.md` | Radius named, proof named, no hard-stop path |
| 4 | Build, implementing | The diff | Confined to the radius |
| 5 | Test | Proof output | Suite shape holds; the test was red without the change |
| 6 | Review | Findings against the review policy | Verdict recorded |
| 7 | QA | `qa.md` | Criteria met on a live Session |
| 8 | Document | Doc updates or a cleared list | Nothing coupled is left unaddressed |
| 9 | Integrate | PR merged, ticket closed | Every artifact present |
| 10 | Maintain | A new `intent.md` | A control band was breached |

[stages.md](stages.md) has what each consumes, produces and refuses, in the
same seven slots per stage ([stage-template.md](stage-template.md)). It is the
only home of stage instructions. In an interactive session,
`.claude/skills/factory/SKILL.md` routes to the right section and copies none
of it.

## The rest

- **[design.md](design.md)** — the agreed target design (2026-10-22) and its
  build order. Not yet built: each part becomes true when its ticket merges.
- **[roles.md](roles.md)** — who performs each stage, what each may write, and
  the one rule that generates all of them.
- **[artifacts.md](artifacts.md)** — the `.factory/<n>/` chain and the
  front-matter contract per file. This is the contract a parser implements.
- **[bootstrap.md](bootstrap.md)** — how to work a ticket *now*, while most of
  the above is **[instruction]** rather than **[mechanical]**. **Read this
  before your first ticket.**
- **[merge-policy.md](merge-policy.md)** — what CI merges without a person, and
  why no agent ever merges. `factory merge check <pr>` shows what CI will
  decide.

## What this does not restate

`AGENTS.md` owns the repo's standing rules: the green baseline, what may not be
changed without asking, when to stop and hand back. `CONTEXT.md` owns the domain
vocabulary. `docs/adr/` owns architectural decisions. `factory/AGENTS.md` owns
the `factory` package's own rules and the exit-code contract.

Each of those is stated once, in its own place, and referenced from here. If
this page and one of them disagree, they are wrong and this page is wrong — say
so on a ticket rather than picking one.
