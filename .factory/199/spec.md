---
ticket: 199
stage: design
method: suite
criteria:
  - all three hooks invoke an interpreter path that resolves with no activated venv
  - the invocation is proven from a shell with a minimal PATH, not a developer shell
  - a hook that cannot run writes to stderr rather than failing silently
  - docs/factory/ records that hooks fail open, so the next person checks rather than assumes
  - the decision logic is unchanged, this being an invocation fix only
specified_by: claude
specified_at: 2026-10-17
reviewed_by: see spec-review.md
---

# Spec: make the hooks actually run

## Source

Issue #199. Found by reading the #194 worker's pane, not by a test.

## The fix

    "${CLAUDE_PROJECT_DIR:-.}/.venv/Scripts/python.exe" -m factory hook <event>

`CLAUDE_PROJECT_DIR` is supplied by Claude Code. `python -m factory` removes the
dependency on a console script being on `PATH`.

## Out of scope, deliberately

Making hooks fail **closed** on a broken toolchain. That is a real decision with
a real downside — a repo nobody can commit to — and it belongs in the
`SessionStart` verification question raised in `intent.md`, not smuggled into an
invocation fix.

## Verification method: suite

The decision functions already have tests and are untouched. What this ticket
adds is a test that the *configured command string* resolves: it can be executed
from a minimal environment and returns valid hook JSON.

## Known gap

`specified_by` is the Builder. Review stand-in is the mitigation.
