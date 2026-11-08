---
name: orchestrate
description: Run an epic's tickets to completion. Start a fresh agent per ticket through Herdr (the app), watch each one to a merged PR into the epic branch, and come back to the maintainer only when they are needed. Use when the maintainer asks to orchestrate, run or work through an epic, or invokes /orchestrate.
argument-hint: <epic issue number>
---

# /orchestrate: run one epic's tickets

The rules live in `docs/agents/orchestrating.md`. Read it first; this file
only says how to start.

Agents are managed with **Herdr** (the app) through its `hc` CLI: `hc --skill`
prints its manual. `herdr-app --skill` covers the window and is rarely needed.
Worktrees are plain `git worktree`. The old `herdr` terminal CLI is gone.

1. Check `HC_TERMINAL_ID` is set and `hc ls` works. If not, tell the
   maintainer to start this session inside the Herdr app, and stop.
2. Read the epic named in the argument, then follow `orchestrating.md` from
   "Before the first ticket".
3. You write no code: every change comes from a ticket agent. You do read
   code to settle a review dispute ("Disputes" in `orchestrating.md`), and
   you only bring the maintainer what agents and you cannot resolve.
