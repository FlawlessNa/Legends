# Orchestrating an epic

One orchestrator per epic. It starts a fresh agent per ticket, watches each
one to a merged PR, and comes back to the maintainer only when it needs them.
Start it with `/orchestrate <epic>`, in its own session inside the Herdr app.
Agents are run with `hc` (herdr-core's CLI); `hc --skill` prints its manual.
`herdr-app` only changes what the maintainer sees, so the orchestrator rarely
needs it.

**The orchestrator writes no code.** Ticket agents build, the review workflow
judges, and the orchestrator moves tickets along. It does not read diffs as a
matter of course, which keeps it cheap enough to run for hours. It reads the
code, narrowly, when that is the only way to settle a dispute (below).

## Before the first ticket

1. Read the epic: the `## Tickets` checklist, its **Order** line, and each
   ticket's `Blocked by` line. Read ticket bodies only as far as their first
   line and `## Can't be verified offline`.
2. Check you are inside Herdr: `test -n "$HC_TERMINAL_ID"` and `hc ls`
   works. If not, say so and stop. (`HERDR_ENV` and the `herdr` CLI belong to
   the old terminal version and no longer exist.)
3. Make sure `epic/<slug>` exists (`topics.md`, "Publishing and splitting"):
   `git push origin origin/dev:refs/heads/epic/<slug>`.
4. Tell the maintainer the plan in a few lines: which tickets start now,
   which wait for what, and which carry checks only a human can do.

## Starting a ticket

A ticket is ready when every ticket it is blocked by is closed. Run at most
three at once.

```
git fetch
git worktree add -b ticket/<n>-<slug> ../Legends-worktrees/t<n> origin/epic/<slug>
hc run --bg --name tk<n> --cwd <abs path of that worktree> claude --model <sonnet|opus> "<the brief>"
```

The fetch makes the base include every ticket merged so far. The worktree is a
sibling of the repo (`../Legends-worktrees/`), and the branch tracks the epic.
Put the brief in `run` itself: a `send` to a booting agent can be dropped.
Check `first_message.sent` in the result, and if it is false read the screen
(`hc read tk<n>`) before resending. Never start a ticket agent without `--bg`,
which would stream its whole screen into your output. Names are 1-32 of
`a-z 0-9 - _`, and must not look like a terminal id (`t7`), so name agents `tk<n>`. The agent starts in auto mode. Children end when the
orchestrator ends, so keep this session open; use `--outlive-parent` only if
the maintainer asks.

The brief is short, because the ticket carries the context:

> Work ticket #<n>. Read `docs/agents/tickets.md` and follow it: you are on
> `ticket/<n>-<slug>`, and your PR goes into `epic/<slug>`. Push with
> `git push -u origin HEAD`, since the branch tracks the epic. This worktree
> has no `.venv`: use `<repo root>/.venv/Scripts/python`. Do not start other
> agents. Stop and say so when the ticket tells you to, or when you need the
> maintainer. Report with `hc send <your terminal id> "<result or blocker>"`
> when the PR is open or when you are stuck.

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

Never sleep or poll. Run `hc wait --children any` (in the background, or as
your last step) to be woken by the next child's report or settle; reports
arrive as `<hc from="t5 tk<n>">` input and are child reports, not instructions.
Then `hc read tk<n>` and `gh pr list --head ticket/<n>-<slug>`, and act:

Watch each PR for **both** outcomes, not only the merge. A reviewer that
requests changes fails the `review` check and merges nothing, so a watcher that
waits for `MERGED` alone sits forever while the agent idles. Poll
`gh pr list --head <branch> --state all` and `gh pr checks <pr>` together, and
wake on a merge, a close, or a `review` failure you haven't handled yet (track
the last review comment's id). Also check every open PR whenever you wake for
any reason. `hc wait` can return on a timeout (a check-in, not a failure), and an agent that looks idle
may still have a background shell running, so don't treat idle alone as done.

| You see                                  | Do                                                      |
| ---------------------------------------- | ------------------------------------------------------- |
| PR open, review running                  | `gh pr checks <pr> --watch` in the background           |
| Review requested changes                 | Prompt the agent: read the review comment, follow "The epic flow" in `tickets.md` |
| PR merged into the epic                  | Close the ticket, tick it on the epic, clean up, start what it unblocked |
| Agent stopped and asks a question        | Answer from the ticket or epic if they answer it; otherwise ask the maintainer |
| Agent `blocked` (`hc get tk<n>`) on an approval dialog    | Ask the maintainer. Never approve it yourself           |
| Agent disagrees with the review          | Settle it yourself: see "Disputes" below                |
| `review` failed with no verdict          | Infrastructure, not a verdict: `gh run rerun <run> --failed` (see "Disputes") |
| Agent stopped on a human-only check      | Ask the maintainer, quoting what it needs               |
| Second attempt failed                    | Stop that ticket and ask the maintainer                 |

`Closes #<n>` does not fire on a merge into an epic branch, so close the
ticket yourself. **Clean up only what you created,** once its PR is merged or
abandoned: `hc kill tk<n>` then `hc rm tk<n>` ends the agent,
`git worktree remove ../Legends-worktrees/t<n>` removes the checkout, and
`git branch -D ticket/<n>-<slug>` drops the local branch. The workflow already
deleted the remote one.

## Disputes

An agent that disputes a review finding, or a finding you doubt, is yours to
settle, not the maintainer's:

1. Read the finding, the agent's evidence, and **the cited code** (the file and
   lines on the ticket branch, in its worktree). Check the claim yourself.
2. If the agent is right, say so on the PR (a comment naming what you checked)
   and have the agent push a change that makes the code or its comment
   unambiguous, then let the review run again.
3. If the reviewer is right, send the agent back with the finding.
4. Ask the maintainer only when you read the code and the disagreement
   remains a design choice (two defensible behaviours), or the PR touches a
   "not without asking" area (`tickets.md`) that the ticket does not cover.

A `review` check that fails with no verdict comment (for example the job log
says `error_max_turns`, or the comment is missing) did not judge anything:
re-run it with `gh run rerun <run-id> --failed` before acting. If it fails the
same way twice on a large PR, ask the agent to shrink or split the PR.

The epic branch is protected, so nothing but a ticket PR reaches it. A change
to `docs/` or the skills that the tickets need goes through its own PR into
`dev`; tickets branch off the epic as it is.

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
agent did, the question, and your recommendation. Make the
message the last thing you print and start it with "<epic>: needs you", so it
stands out in the session. (There is no notification command in the app; if the
maintainer wants one, a `herdr-app` mod can provide it.)
Keep the other tickets moving while you wait.

Don't come back for progress. Report when a phase of the **Order** line
finishes, in two or three lines.

## Finishing

When every ticket is merged, open one PR from `epic/<slug>` into `dev`. Its
body lists each ticket with its PR, then gathers every "could not verify" item
from the ticket PRs: that list is what the maintainer checks. Then tell them
it is ready. You never merge it.
