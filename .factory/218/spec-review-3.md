---
ticket: 218
stage: design
cycle: 3
verdict: pass
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "write patterns are globs matched the way merge.py matches paths (full_match, ** crosses directories), with a leading ! excluding, so the documenter's scope can say docs/**, **/AGENTS.md (excluding .claude/**), CONTEXT.md and .factory/<n>/park.md while excluding every merge.POLICY hard-stop and protected docs path, taken from merge.py rather than copied, and scope(role, ticket) substitutes <n>"
---

# Spec review, cycle 3: roles.py, the model table, and configs/factory.toml

**Verdict: `pass`.** I checked R1–R4 and notes a–f from `spec-review-2.md`
against `spec.md` and `intent.md` at `304d3e6`. All four required items are
resolved in the criteria, and every note is answered or explicitly placed.

Three small notes remain. None of them changes what a criterion requires, so
the plan can settle each one, and must.

## Required items

| Item | Resolved by |
| --- | --- |
| R1 `Stage` | Criterion 1 adds `spec-review` and `accept`, keeps every v1 member, and leaves v1 `ROWS`, `VERDICTS` and `test_routing.py` unchanged. |
| R2 `dispatched` ordering | Criterion 8: "computed on the state before the dispatch is recorded", and `factory model <n>` reports the next dispatch's model. "Not in scope" puts the before-recording obligation on #159, with a test here. |
| R3 `--json` | Criterion 4: the command words after the global options, naming `["--json", "spec", "submit"]`. |
| R4 timing keys | Criterion 10:<br>• `worker_timeout_min` and `poll_s` are optional;<br>• `attempts`, `cycles` and `wip` are positive integers, and `launcher` is a string;<br>• `ConfigError` maps to exit 3, naming the key. |

## Notes from cycle 2

| Note | Status |
| --- | --- |
| a. Unowned after the split | Criterion 11 adds #237 to §10 and points the Supersedes notes at #237. The coordinator reports that the `stages.md` items were posted to #237, and that #159's blockers already include #237. I did not check GitHub. |
| b. §6 vs §2 | Criterion 11 marks §6's staleness sentence "settled by #237". The coordinator reports a comment on #186. |
| c. `[roles]` | Criterion 7 adds `resolve_role(table, role)`. A key that is not a role, or a role with stages, is a `TableError`. |
| d. Scopes and commands | Criteria 2 and 5:<br>• the Documenter's scope adds `park.md`;<br>• `**/AGENTS.md` excludes `.claude/**`;<br>• its exclusions come from `merge.POLICY`;<br>• `role_for(plan\|test)` is None.<br>The Planner already has `park`, since "Judges: park" covers it. |
| e. Intent | `intent.md` gains "Split, 2026-10-23". |
| f. v1 rows route v2 until #237 | Recorded under "Not in scope", and the PR says so. |

## Remaining notes for the plan

**1. The Shape's Documenter scope disagrees with criterion 2.** The Shape still
lists `!docs/adr/**` and `!docs/agents/typing.md` as copied literals, and it
omits `park.md`. The criterion wins, so build from it. Correct the Shape in the
plan so the next reader does not copy it.

**2. "Every `merge.POLICY` hard-stop and protected docs path" needs one stated
rule.** I read it as every entry of `hard_stop_paths` and `protected_paths` that
begins with `docs/`. Today that is `docs/adr/**`, `docs/agents/typing.md` and
`docs/factory/merge-policy.md`.

That rule leaves `factory/AGENTS.md` writable through `**/AGENTS.md`, even
though `factory/**` is protected. The cost is small: a protected path never
auto-merges. But excluding *every* hard-stop and protected pattern is simpler,
and it holds as the lists grow. The plan should pick one rule and test the
`factory/AGENTS.md` case either way.

**3. The intent's "Affected users and systems" list is unchanged.** It still
names `routing.py` without qualification, and `stages.md`. It omits:

- `factory/config.py`;
- `cli.py`;
- `design.md`;
- `artifacts.md`'s Supersedes note.

The split paragraph covers this in prose. The plan's radius is what binds, so
list those paths there. On the timing keys: #220's herdr adapter has only its
own internal timeouts (`launchers/herdr.py:65`). The reader that will supply
`worker_timeout_min` and `poll_s` is #159, not #220.

## Could not verify

- The GitHub-side items: the #237 posts, #159's blockers, and the #186 comment. These were reported by the coordinator, and I read nothing on GitHub this cycle.
- `state.dispatched`'s behaviour, beyond reading it on `issue/219-loop-state` (`factory/state.py:137–147`). It is not on this branch yet.
