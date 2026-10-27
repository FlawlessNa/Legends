# Orchestrating an epic

One orchestrator per epic. It starts a fresh agent per ticket, watches each
one to a merged PR, and comes back to the maintainer only when it needs them.
Start it with `/orchestrate <epic>`, in its own session inside Herdr.

**The orchestrator reads no code and writes none.** Ticket agents build, the
review workflow judges, and the orchestrator moves tickets along. Keeping it
out of diffs is what keeps it cheap enough to run for hours.

## Before the first ticket

1. Read the epic: the `## Tickets` checklist, its **Order** line, and each
   ticket's `Blocked by` line. Read ticket bodies only as far as their first
   line and `## Can't be verified offline`.
2. Check you are inside Herdr: `test "$HERDR_ENV" = 1`. If not, say so and
   stop.
3. Make sure `epic/<slug>` exists (`topics.md`, "Publishing and splitting"):
   `git push origin origin/dev:refs/heads/epic/<slug>`.
4. Tell the maintainer the plan in a few lines: which tickets start now,
   which wait for what, and which carry checks only a human can do.

## Starting a ticket

A ticket is ready when every ticket it is blocked by is closed. Run at most
three at once.

```
git fetch
herdr worktree create --branch ticket/<n>-<slug> --base origin/epic/<slug> --no-focus
herdr agent start t<n> --kind claude --pane <.result.root_pane.pane_id> -- --model <sonnet|opus>
herdr agent prompt t<n> "<the brief>"
```

The fetch makes the base include every ticket merged so far. The worktree
gets its own Herdr workspace under `~/.herdr/worktrees/`, and the agent starts
in auto mode. Read IDs from each command's JSON, never guess them.

The brief is short, because the ticket carries the context:

> Work ticket #<n>. Read `docs/agents/tickets.md` and follow it: you are on
> `ticket/<n>-<slug>`, and your PR goes into `epic/<slug>`. Push with
> `git push -u origin HEAD`, since the branch tracks the epic. This worktree
> has no `.venv`: use `<repo root>/.venv/Scripts/python`. Stop and say so when
> the ticket tells you to, or when you need the maintainer.

### Choosing the model

Pick per ticket, and give the choice and the reason in the plan you show the
maintainer, who can override it.

- **Sonnet by default:** the ticket is well specified, and its acceptance
  criteria pin the behaviour down.
- **Opus when the ticket needs judgment its body can't fully carry:**
  - it crosses the spec threshold on its own (`topics.md`);
  - it designs an interface that later tickets build on;
  - it decodes or ports something subtle, where tests may miss a wrong answer.

### A second attempt

A ticket's first agent has **failed** when it:

- stopped without a PR, for a reason that is not in "When to stop and hand
  back" (`tickets.md`);
- got three request-changes reviews in a row;
- stalled: it settled again without progress after you prompted it to carry
  on.

Then close its PR, if any, and start a fresh agent **on Opus** in a fresh
worktree off the current epic branch. Add to the brief what the first attempt
ran into, with a link to its PR. If the second attempt fails too, stop that
ticket and ask the maintainer.

## Watching

Run `herdr agent wait t<n>` as a background job for each live agent, so you
are woken when it settles rather than polling. Then `herdr agent read t<n>`
and `gh pr list --head ticket/<n>-<slug>`, and act:

Watch each PR for **both** outcomes, not only the merge. A reviewer that
requests changes fails the `review` check and merges nothing, so a watcher that
waits for `MERGED` alone sits forever while the agent idles. Poll
`gh pr list --head <branch> --state all` and `gh pr checks <pr>` together, and
wake on a merge, a close, or a `review` failure you haven't handled yet (track
the last review comment's id). Also check every open PR whenever you wake for
any reason. `herdr agent wait` can miss a settle, and an agent that looks idle
may still have a background shell running, so don't treat idle alone as done.

| You see                                  | Do                                                      |
| ---------------------------------------- | ------------------------------------------------------- |
| PR open, review running                  | `gh pr checks <pr> --watch` in the background           |
| Review requested changes                 | Prompt the agent: read the review comment, follow "The epic flow" in `tickets.md` |
| PR merged into the epic                  | Close the ticket, tick it on the epic, clean up, start what it unblocked |
| Agent stopped and asks a question        | Answer from the ticket or epic if they answer it; otherwise ask the maintainer |
| Agent `blocked` on an approval dialog    | Ask the maintainer. Never approve it yourself           |
| Agent disagrees with the review          | Ask the maintainer: they decide                         |
| Agent stopped on a human-only check      | Ask the maintainer, quoting what it needs               |
| Second attempt failed                    | Stop that ticket and ask the maintainer                 |

`Closes #<n>` does not fire on a merge into an epic branch, so close the
ticket yourself. **Clean up only what you created,** once its PR is merged or
abandoned: `herdr worktree remove --workspace <id>` closes the agent and its
workspace, then `git branch -D ticket/<n>-<slug>` drops the local branch. The
workflow already deleted the remote one.

## Coming back to the maintainer

**Decide first whether to ask at all.** If the question has one obvious,
low-risk answer (a ticket needs a small amendment, a finding has a single
sensible reading), make the change yourself: comment on the ticket or
brief the agent, and mention it in the next phase report. Ask only when the
options differ in ways the maintainer would care about.

**Write for someone who hasn't seen the tickets.** The maintainer took part in
the intent and spec, not in splitting or reviewing the tickets. Don't cite
ticket numbers, field names or internal terms they've never seen: say what is
being built and what happened in plain words, and name a ticket only as a
pointer.

Ask in one message, with everything they need to answer: the ticket, what the
agent did, the question, and your recommendation. Raise
`herdr notification show "<epic>: needs you" --sound request` so they notice.
Keep the other tickets moving while you wait.

Don't come back for progress. Report when a phase of the **Order** line
finishes, in two or three lines.

## Finishing

When every ticket is merged, open one PR from `epic/<slug>` into `dev`. Its
body lists each ticket with its PR, then gathers every "could not verify" item
from the ticket PRs: that list is what the maintainer checks. Then tell them
it is ready. You never merge it.
