---
ticket: 194
stage: plan
accepted_by: nassim
accepted_at: 2026-10-17
---

# Intent: CI decides what merges, no agent does

## Problem statement

Every PR waits for Nassim, including the ones nothing in the bot can be harmed
by. His stated bottleneck is his own input, and this is the largest class of
work that costs it.

An allowance granted in conversation does not solve it. Each ticket gets a fresh
agent, and permission granted in one conversation does not reach the next: a
handoff prompt carrying "you may merge" is indistinguishable, to the agent
reading it, from an earlier agent's opinion. A written policy an agent applies
is better, but still ends in **self-merge** — the agent that wrote the diff
decides its own diff is mergeable, and no reviewer ever looks.

## Proposed outcome

A workflow evaluates a committed policy on every PR and merges when **all** of
its conditions hold. Neither the implementing agent nor Nassim is in the
decision. An agent cannot merge its own work because an agent cannot merge at
all.

The eight conditions, from the issue body: the PR closes exactly one ticket;
that ticket is `type:chore` or `type:refactor`; it is `method:suite`; the diff
touches only `factory/**`, `docs/**`, `.claude/**`, `tests/test_factory/**`; no
`AGENTS.md` hard-stop path appears in it; every required check is green; the
PR body's "Could not verify" section is present and non-empty; the base is the
working branch. Anything failing any condition waits for a human. **The default
is to wait.**

`factory merge check <pr>` runs the same evaluation locally, so an agent can see
what CI will decide without guessing.

This is `auto_merge_types` (#160) at its first notch, before the Foreman
exists. It widens only by editing the committed policy, so `git log` answers
"when did we start trusting this, and who decided".

## Affected users and systems

- Nassim, who stops being the merge step for factory-plumbing tickets.
- Every agent PR: each is evaluated, and most are told to wait.
- `.github/`, which has no workflows today. This is the first.
- The `factory` package, which grows a `merge` command.
- #151, which keeps the PR checks this policy reads (suite and linters) and the
  `pre-push` hook.
- #160, whose dial this starts.

## Constraints

- **The paths it may merge cannot reach the bot.** Nothing in `botting/` or
  `maple/` imports `factory/`, `docs/`, `.claude/` or `tests/test_factory/`, so
  a wrong merge costs a revert.
- **The hard-stop list holds under any circumstances**, independently of the
  path allowlist, so widening one cannot relax the other.
- **Widening is a commit**, never a conversation, a repo setting or a handoff
  prompt.
- The local check and CI must give the same answer.

## Open questions

- **Acceptance is inferred.** Nassim wrote the issue body and directed this
  session to work the ticket; `accepted_by` records that, not a separate
  sign-off on this file.
- **The body's dependency line is stale.** It still reads "Depends on #151 for
  the first workflow". Nassim's own comment on the issue resolves it: this
  ticket creates the first workflow, and its dependencies are none unmet. Stage
  1 says to have the body amended rather than build from a comment; editing the
  issue from this session was refused by the harness's permission check, so the
  amendment is a handoff item in the PR. This intent follows the comment.
- Condition 6 names checks — the suite shape, `ruff check`, `ruff format`,
  `pyright` — that no workflow produces today; #151 owns producing them. Until
  it does, condition 6 cannot hold. Whether that makes the policy inert until
  #151 lands is settled in `spec.md`.
