---
ticket: 220
stage: plan
accepted_by: nassim
accepted_at: 2026-10-22
---

# Intent: a launcher that starts, watches and stops workers, with herdr behind it

## Problem statement

The factory loop (#159) has to start a worker for a stage, watch it until its
turn settles, read its Claude session id, and stop it before judging the turn.
Nothing in `factory/` can do any of that today. The agreed design
(`docs/factory/design.md` §4 rule 1, §5, §8) puts that behind an interface so
the loop's decisions stay pure and testable, with herdr as the only
implementation.

Two facts from the live run on #215 (2026-10-22) make the launcher more than a
thin wrapper:

- **The folder-trust dialog.** A fresh folder raises Claude Code's trust
  dialog, which blocks startup (`agent_not_ready`, then `blocked`), and its
  default is "No, exit". Every first dispatch into a fresh worktree would fail.
- **Workers inherit the maintainer's auto permission mode**, which approved
  unlisted commands such as `git status` and `python -c`. A worker that holds
  the maintainer's GitHub token or git credential helper can push or call
  GitHub by mistake. Ruling R11 says workers hold neither.

## Proposed outcome

- `factory/launcher.py` defines `WorkerSpec`, `Handle`, `WorkerState` and the
  `Launcher` protocol from the issue body, plus the one function that builds a
  worker's environment with the credentials stripped (R11).
- `factory/launchers/herdr.py` implements it over the herdr CLI: an idempotent
  `start` that also answers the trust dialog for worktrees of this repository,
  the state mapping, the session id, and a `stop` that never touches a designer
  pane and returns only once the worker's process tree is gone (re-check X3).
- A `FakeLauncher` that later tickets' tests use in place of herdr.
- `docs/factory/design.md` §8 and §12 updated with what #215 settled, as #215's
  closing comment asks.

## Affected users and systems

- The factory loop (#159) and `factory feature new` (#222), which will call the
  launcher. Neither exists yet. Nothing calls the launcher when this lands.
- herdr 0.9.5 and Claude Code worker sessions, at run time only.
- `factory/`, `tests/test_factory/` and `docs/factory/design.md`. No bot code,
  no configuration, no `.claude/` settings.

## Constraints

- **The suite cannot drive herdr.** The adapter is tested against recorded herdr
  JSON. No pane is created and no agent started while building this ticket;
  #215 is the live evidence.
- Where #215 contradicts design §8, this ticket follows #215 (issue body).
- `factory` imports neither `botting` nor `maple`, and gains no dependency.
  `psutil` is installed in the venv but declared nowhere, and declaring it
  touches a hard-stop path (`AGENTS.md`).
- Credential stripping guards against error, not intent (design §4 rule 6). A
  worker can unset its env.

## Open questions

- **Acceptance is inferred.** The maintainer wrote the issue body and the #215
  comments, and said to "keep working on the next tickets" (2026-10-22).
  `accepted_by: nassim` records that instruction, not a reading of this file.
- **#207 is listed as a blocker on GitHub and is still open.** It changes the
  Stop hook. The launcher shares no code with it, so this ticket proceeds; the
  link matters for the loop, which needs both.
- **The trust dialog's key sequence.** #220's comment says to answer it with
  `down enter`. #215 recorded the default as "No, exit" but not the option
  order, so the sequence is taken from the comment and cannot be confirmed
  offline.
