---
ticket: 202
stage: design
method: suite
criteria:
  - POLICY.allowed_paths does not contain .claude/** and a test asserts a PR touching .claude/settings.json is refused on paths
  - POLICY.allowed_paths contains .factory/** and a test asserts an artifact-only PR is not refused on paths
  - session_report returns the heartbeat line on a non-ticket branch and nothing else
  - session_report still returns the full chain report on a ticket branch
  - a test asserts the heartbeat is present off a ticket branch, so a silent hook cannot pass
  - docs/factory/merge-policy.md states why .claude/** is excluded
  - hard_stop_paths is unchanged, and the test that they are checked independently still passes
specified_by: claude
specified_at: 2026-10-18
reviewed_by: see spec-review.md
---

# Spec: first-run corrections

## Source

Issue #202. Found by running the factory on itself, not by review.

## Why `.claude/**` and not a narrower rule

`.claude/settings.json` alone would be the minimal fix, but `.claude/skills/`
routes agents and `.claude/hooks/` holds the launcher — all three change what is
enforced. The whole directory is the honest boundary.

## What this does not fix

The policy trusts labels an agent can set. Excluding `.claude/**` removes the
worst consequence; the cause is label trust and only #163's per-role write
scopes address it. Recorded, not solved.

## Known gap

`specified_by` is the Builder again (#180).
