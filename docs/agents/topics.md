# Discussing a topic

The point is that the maintainer and the agent agree on what to build before
anything changes. The agreement belongs to a **topic**, not to each ticket: a
topic is discussed once, then split into tickets that inherit the agreement.

Start a topic with `/intent`.

## The phases

1. **Intent.** Discuss until the maintainer says you agree. Ask before you
   propose — what they want, and why, only they can answer. Restate it in your
   own words.
2. **Spec, only past the threshold** (below). The threshold is checked once the
   intent is agreed. If it is crossed, write the spec and discuss it until the
   maintainer approves it.
3. **Tickets.** Once the spec is approved (or the intent, if no spec was
   needed), draft the tickets. If there is a spec, have them reviewed
   independently (below). Then the maintainer approves the list of tickets,
   not each body, and you publish the epic.

**A standalone ticket carries its own intent.** A clear bug with a clear
acceptance test, labelled `ready-for-agent`, needs no topic: see `tickets.md`.

## The discussion page

The discussion happens on a lavish page, under `.lavish/<topic>/`, which is
gitignored:

```
.lavish/<topic>/index.html         the page, started from the /intent template
.lavish/<topic>/intent.md          the working copy of the intent
.lavish/<topic>/spec.md            the working copy of the spec, if needed
.lavish/<topic>/draft-tickets.md   the drafted tickets, then the review
```

The page has these sections, in order. It grows a section per phase:

1. **Context:** what exists today, the maintainer's goals, and what is already
   settled.
2. **Decisions:** one card per open question, with options, their costs, a
   recommendation, and answer controls. A settled decision collapses to a
   short card that records the answer.
3. **`intent.md`:** rendered from the file.
4. **`spec.md`:** rendered from the file, once past the threshold, with an
   approve control.
5. **`draft-tickets.md`:** the drafted tickets and the review's findings,
   rendered the same way, with an approve control for the list.

### Rules

- **Every block has a stable `data-block` id**, and keeps it across
  iterations. Each `##` section of a rendered `.md` file is a block
  automatically.
- **Render after every edit, before replying.** Lavish runs the page in a
  sandboxed iframe that cannot read files, and the render step does two
  things. It inlines `intent.md` and `spec.md` into the page. It also embeds
  the previous iteration, so the page highlights every new, changed or removed
  block in a bar at the top:

  ```
  node .claude/skills/intent/render.mjs .lavish/<topic>
  ```

- **Edit `intent.md` and `spec.md`, never their rendered copy.** The files are
  the source; the page shows them.
- **Run lavish pinned:** `npx -y lavish-axi@0.1.92 <page>`, and `poll` for
  feedback. Bump the version deliberately. The unpinned `npx -y` in the lavish
  skill fetches whatever was published last.

## `intent.md`: what and why, about one screen

```
# Intent: <topic>
Status: draft | agreed <date>

## Problem              why this topic exists now
## Outcomes             what is true when it is done, in the maintainer's terms
## Success looks like   how the maintainer would recognise it
## Principles and constraints
## Out of scope
## Open questions       until agreed, then "None"
```

**Keep it short.** Every ticket agent reads it in full, and it changes rarely,
because outcomes outlive designs. A diagram or a file path in it is spec
material leaking in.

## The spec threshold

A spec is required when the change does any of these:

- alters which keys reach the game, or when: the input send path, focus
  handling, or the Held-Keys Ledger (ADR 0002);
- touches an area an ADR decides, or the telemetry envelope (ADR 0001);
- changes a format something else reads: a config, map JSON, an interface
  between modules, or a workflow;
- spans more than one package, or adds a module;
- can only be verified against a running client.

Below it, the agreed intent is enough.

## `spec.md`: how, and how we will know

```
# Spec: <topic>
Status: draft | approved <date>

## What changes              modules, interfaces, formats; before and after
## Decisions                 with the alternatives rejected, and why
## Acceptance criteria       each checkable by a test or by reading the diff
## Can't be verified offline
## Proposed tickets
```

**It may be as long as it needs.** No agent reads it in full: each ticket
names the sections it needs.

## The independent review

The agent that wrote the spec is the worst judge of it: it fills the gaps from
the conversation without noticing. So once the tickets are drafted, and before
the maintainer sees the list, a reviewer with **none of the conversation**
checks them. It runs whenever there is a spec.

- **Who:** a fresh subagent on the strongest model, or a fresh session. Give
  it only the paths to `intent.md`, `spec.md` and `draft-tickets.md`, and
  the task below. Do not summarise the discussion for it: the missing context is what
  it is there to find.
- **The task:**
  1. For each ticket: could you finish it from its body and the documents it
     points at, without asking? List what you would have to guess.
  2. For each acceptance criterion: can a test or a reading of the diff check
     it? If not, it belongs under "Can't be verified offline".
  3. Does anything in the spec or the tickets contradict the intent, or reach
     outside it?
  4. Report findings only, each naming the ticket or section. Change nothing.
- **Once, not a loop.** Fix each finding or argue against it, and record both
  under `## Review` at the end of `draft-tickets.md`: the finding, then
  what you did about it. The maintainer sees what was caught. A finding that would change
  the approved spec goes back to the maintainer as a decision.
- **It blocks nothing.** Its job is to make the list the maintainer approves
  a better one.

This is on trial with the first epics. If it keeps finding nothing a ticket
agent would have tripped over, drop it.

## Publishing and splitting

Once the maintainer approves the list of tickets:

1. Create the epic: `gh issue create --label epic`. Its body is `intent.md`,
   then `spec.md`, then a `## Tickets` checklist. The epic is the durable
   record; the `.lavish/` files are not.
2. File each ticket, link it as a sub-issue of the epic (see
   `issue-tracker.md`), and add it to the checklist.
3. The agent that ran the discussion writes the tickets, while it still has
   the full context, and files them as drafted and reviewed.
4. Create the epic branch off `dev`:
   `git push origin origin/dev:refs/heads/epic/<slug>`. Tickets merge into it
   through the epic flow (`tickets.md`). Skip this when every ticket can land
   on `dev` on its own and the maintainer prefers to merge each one.

### The ticket template

A fresh agent must be able to finish a ticket from its body alone:

```
Part of #<epic>  ·  Blocked by #<n> (if any)

## Goal
One or two lines: what is true afterwards.

## Acceptance
- [ ] Checkable by a test, or by reading the diff

## Where to look
- Intent: #<epic>, always read in full
- Spec: #<epic> § "<section>" (only the sections this ticket needs)
- path/to/file.py: what changes there
- docs/agents/<doc>.md § "<section>"

## Constraints
ADRs that apply, and what must not be touched.

## Can't be verified offline
What a human or a live session must confirm.
```

Copy the goal and the acceptance criteria into the ticket, so it stands alone.
Point at the intent, spec sections, files and docs rather than copying them.
