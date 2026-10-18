---
ticket: 199
verdict: changes-requested
reviewed_by: explore-subagent (read-only, no write access)
reviewed_at: 2026-10-17
transcribed_by: claude
---

# Spec review: #199

Read-only agent, given `intent.md` and `spec.md` only, told not to read the
implementation. Eight findings. The first one is the important one.

## Finding 1 — ACTED ON. The criterion was satisfied by the bug it prevents.

> "Criterion 3 is satisfied by the bug it is meant to prevent. 'a hook that
> cannot run writes to stderr rather than failing silently' — the #189 failure
> *did* write to stderr (`factory: command not found`, surfaced as `Stop hook
> error: Failed with non-blocking status code`) and still went unnoticed for a
> day. A criterion that the broken state already passes cannot discriminate fix
> from bug."

That is correct and it invalidates the criterion. stderr was never the problem.

**The deeper point, which the reviewer reached in its fail-open section:** a hook
that cannot run emits nothing, and nothing it emits can report that. So no
error-based signal works. The signal has to be a line whose **presence** proves
the toolchain is reachable.

Added: `session_report` opens with `factory gates: LIVE`, and the entry skill's
step 0 tells an agent to say so loudly if that line is missing. Absence is now
the alarm, and absence is something an agent can actually observe.

## Fail-open, verbatim, because the reasoning is better than mine

> "Deferring **fatal** is correct and well argued... But the spec defers
> **detection** along with it, and those are separable. The `SessionStart` probe
> the intent asks about is not an enforcement change — it reports, it does not
> block, and it is precisely what makes a dead `factory` distinguishable from a
> `factory` that allowed the action... the ticket fixes today's instance without
> touching the property that let the instance hide."

Conflating detection with enforcement was the error. Detection is now in;
fail-closed stays out.

## Finding 4 — PARTIALLY ACTED ON, and a residual risk is recorded

> "If `CLAUDE_PROJECT_DIR` is unset, the command becomes
> `./.venv/Scripts/python.exe`, which exits 127 from any cwd other than the
> project root — silently, non-blocking, indistinguishable from an allow."

Real, and it survives the launcher: `bash "${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/factory-hook.sh"`
cannot find the script if that variable is unset and the cwd is elsewhere. There
is no way to express "find the repo" in a settings string without *some* anchor.

What the heartbeat buys is that this failure is now **observable**: no
`factory gates: LIVE` line means the gates are dead, whatever the cause.
Recorded as a residual risk rather than claimed fixed.

## Findings not acted on, and why

- **2 — "minimal PATH" is unbound.** Correct. The test scrubs `VIRTUAL_ENV`,
  `PYTHONHOME`, `PYTHONPATH` and the venv from `PATH`, which is stricter than
  the criterion says, but the criterion should have said it.
- **3 — platform-blind.** The launcher tries `Scripts/python.exe` *and*
  `bin/python`, so POSIX works; the criterion never said it had to.
- **5 — dependents undispositioned.** The launcher is now the single place the
  invocation is defined, which is what the finding asks for; no criterion
  requires it.
- **6 — the open question closed by omission.** Acted on by implementing the
  probe instead of deferring it.
- **7 — criterion 4 mixes checkable and unverifiable clauses.** Correct.
- **8 — the suite needs a negative control.**
  `test_the_command_does_not_depend_on_an_activated_venv` is exactly that: it
  fails against the pre-fix `factory hook <event>` form. And
  `_configured_commands()` reads `.claude/settings.json` as the source of truth
  rather than restating the string, which is finding 8(i).

Findings 2, 3, 5 and 7 are all the same shape: the criteria were written loosely
and the implementation happens to be stricter than they demand. That is luck,
not rigour, and it is the Specifier's to fix — which is the Builder here, so it
is recorded instead.
