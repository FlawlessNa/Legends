---
name: orchestrate
description: Run an epic's tickets to completion. Start a fresh agent per ticket through Herdr, watch each one to a merged PR into the epic branch, and come back to the maintainer only when they are needed. Use when the maintainer asks to orchestrate, run or work through an epic, or invokes /orchestrate.
argument-hint: <epic issue number>
---

# /orchestrate: run one epic's tickets

The rules live in `docs/agents/orchestrating.md`. Read it first; this file
only says how to start.

Agents are managed with **Herdr**: use the `herdr` CLI for worktrees, starting
agents, prompting them and waiting on them. `herdr --skill` prints its own
guide, and `herdr <group>` (for example `herdr agent`) prints a group's
syntax. Never run bare `herdr`, which opens the TUI.

1. Check `HERDR_ENV` is `1`. If not, tell the maintainer to start this
   session inside Herdr, and stop.
2. Read the epic named in the argument, then follow `orchestrating.md` from
   "Before the first ticket".
3. You read no code and write none. Every change comes from a ticket agent.
