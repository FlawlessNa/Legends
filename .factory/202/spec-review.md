---
ticket: 202
verdict: pass-with-notes
reviewed_by: claude (no independent reviewer available this turn)
reviewed_at: 2026-10-18
---

# Spec review: #202 — NOT independent

**This is not a real review and should not be read as one.** The Builder wrote
it. The read-only stand-in was not run, because the three defects were found by
the maintainer and by observation rather than by reasoning about a spec, and
the fixes are each a line.

Recorded as a gap rather than dressed up: #189, #197 and #199 each had a genuine
read-only reviewer that found something the Builder had missed, and this ticket
does not. If any of these three changes is wrong, nothing here would have caught
it.

## What was checked, by the Builder

- Each criterion traces to a numbered defect in `intent.md`.
- Each is decidable: a path is in `allowed_paths` or not; `session_report`
  returns `HEARTBEAT` off a ticket branch or it does not.
- `method: suite` is right — all three are pure functions with no live surface.

## The one thing worth a second pair of eyes

`test_ordinary_branches_are_left_alone` asserted the startup report was empty
off a ticket branch. That assertion is now **wrong by design** and was changed,
which means a test moved to accommodate the change rather than catching it.

That is legitimate here — the behaviour genuinely changed, and three new tests
assert the new one — but it is exactly the shape of edit that hides a
regression, so it is called out rather than buried in the diff.
