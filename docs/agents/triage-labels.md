# Triage Labels

Every open issue carries one triage label, which says who can finish it:

| Label             | Meaning                                                  |
| ----------------- | -------------------------------------------------------- |
| `needs-triage`    | The maintainer has not evaluated it yet                  |
| `needs-info`      | Waiting on more information                              |
| `ready-for-agent` | An agent can finish it offline (defined below)           |
| `ready-for-human` | Needs a human: a live client, a measurement, or a judgment |
| `wontfix`         | Will not be actioned                                     |

## The other labels

- **`type:*`** says what kind of work an issue is: `bug`, `defect-live`,
  `tuning`, `build`, `instrument`, `refactor`, `research`, `chore`,
  `grilling` (a design question to settle by discussion) or `prototype`.
- **`epic`** holds a topic's agreed intent and spec. Its tickets are sub-issues
  (`topics.md`).
- **`live-tooling`** marks work that lets agents observe or drive a live
  session. The topic needs one intent discussion with the maintainer before
  any of its issues are worked, whatever their bodies already say. After that,
  each issue inherits the agreement (`topics.md`).

The triage label decides who can finish an issue. The `type:*` label says what
the issue is. There is no third axis.

## What `ready-for-agent` means here

`ready-for-agent` is not "well specified." A ticket can be perfectly specified and
still be impossible for an agent to finish. The label answers one question:

> **Can this ticket's acceptance criteria be settled without a human watching the
> game?**

Answer it with the distinction `CONTEXT.md` already draws:

- An **Invariant** is decidable offline, with no measured constant. A change that
  satisfies it can be proven correct by `pytest` and by reading the diff.
- An **Expectation** holds only within a tolerance, or only against constants
  measured from the live game. Nothing offline can settle it.

**A ticket whose acceptance rests on any Expectation is `ready-for-human`,**
however thoroughly it is written. Not because an agent cannot do the work — it
often can — but because it cannot know when it is done, and an agent that cannot
tell done from nearly-done will report success.

Today this is a hard boundary rather than a soft one: **no test in the suite is
`live`-marked.** The marker is reserved, and the Expectation side has no
automated coverage at all. So "verify against the game" means a human, every
time.

### Applying it

Ask what would prove the ticket done:

| If the proof is | Label |
| --- | --- |
| A failing test that now passes | `ready-for-agent` |
| A new test asserting an Invariant | `ready-for-agent` |
| A diff readable against an ADR or a documented rule | `ready-for-agent` |
| A number someone measured from a running client | `ready-for-human` |
| "The character stopped drifting" / "the rotation looks right" | `ready-for-human` |
| A minimap trail recorded in the GUI editor | `ready-for-human` |
| A timing or animation constant | `ready-for-human` |

**Mixed tickets split.** A ticket that is 80% offline refactor and 20% "then tune
the constant" is two tickets, and the offline one is `ready-for-agent`. Splitting
it is how the agent-workable part gets done unsupervised; leaving it merged is
how it doesn't get done at all.

**When it is genuinely unclear, it is `ready-for-human`.** The cost of the wrong
call is asymmetric: a mislabelled `ready-for-human` ticket waits, while a
mislabelled `ready-for-agent` ticket produces confident work nobody can trust and
someone has to re-derive.
