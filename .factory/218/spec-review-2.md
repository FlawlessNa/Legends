---
ticket: 218
stage: design
cycle: 2
verdict: changes-requested
reviewed_by: claude (spec reviewer subagent, separate session from the specifier)
reviewed_at: 2026-10-23
criterion_quoted: "configs/factory.toml holds attempts, cycles, wip, launcher, worker_timeout_min and poll_s, is read from the session's own checkout like the model table, and an unknown key, a missing key or a wrong type is exit 3 with the key named, and v1 routing never reads it"
---

# Spec review, cycle 2: roles.py, the model table, and configs/factory.toml

**Verdict: `changes-requested`.** I read `spec.md` at `d6684f5` against:

- the findings that stay with #218 (3, 4, 7, 8, 9, 10, and the `cli.py` part of 13);
- issue #237;
- `state.dispatched` on `issue/219-loop-state` (`b8397f3`, `factory/state.py:137`);
- `merge.py`'s `_matching` and path lists;
- `cli.py`'s top-level parser.

The split is clean, and most of each finding is resolved. Four gaps remain that
a builder cannot settle without inventing a contract. Each has a one-line fix:

- R1. The `Stage` members the table needs are no longer in any criterion.
- R2. `dispatched` is correct only on the state before the dispatch is recorded, and nothing says so.
- R3. `allowed(role, argv)` fails on `factory --json …`.
- R4. Two of `factory.toml`'s required keys are timing constants that nobody has given values for.

## Cycle 1 findings

| # | Status | Where |
| --- | --- | --- |
| 3 | Resolved, with note c | Criterion 7 gives a `[roles]` block for the Orchestrator. `accept` joins `integrate` in `NO_AGENT`. |
| 4 | Resolved in models.py, open across tickets (R2) | Criteria 8 and 9. An int of at least 2, not a bool; `--stage` alone never escalates; a new stage's first dispatch does not escalate. |
| 7 | Resolved | Criterion 12 and "Changed tests" name both tests. |
| 8 | Resolved, with note b | Criterion 11 covers R9, §2, §5, §6, §8 and §11, and the Supersedes notes. |
| 9 | Resolved, with R3 and note d | Criteria 1–6: globs with `!`, `RADIUS`, word prefixes, `hook`, `primary`, `role_for`, and the v1 table kept |
| 10 | Resolved except R4 | Criterion 10: the session's checkout, the full key list, exit 3, no v1 read |
| 13 (cli) | Resolved | The Shape: `_model` maps `StateError` and `UnknownChainVersion` to exit 3. Exit 3 rather than 2 matches `MalformedVerdict`, and is right for a malformed artifact. |

## Required

### R1. `Stage` gains `spec-review` and `accept`, and no criterion says so

**Evidence.**
- The first spec's criterion 11 ("Stage gains spec-review and accept and keeps every v1 member") is gone.
- #237's body does not take it either.
- Criterion 7 still needs it:
  - `spec-review = "complex"` fails to load without `Stage.SPEC_REVIEW` (`_stages_of`, models.py:162–175);
  - `accept` cannot join `NO_AGENT` without `Stage.ACCEPT`.
- Criterion 5's `role_for(stage)` "for every v2 stage" needs both members too.

The split has left the enum with no owner.

**Fix.** Add a criterion here:
- `Stage` gains `spec-review` and `accept`, and keeps every v1 member;
- v1's `ROWS` and `VERDICTS` are unchanged;
- `test_routing.py` passes unmodified.

This is the only `routing.py` change in #218, so name it in the intent's affected systems.

### R2. `dispatched` must be called on the state before the dispatch is recorded

**Evidence.**
- `dispatched(current, stage)` returns `attempt + 1` when `current.stage == stage`, and 1 otherwise (state.py:137–147).
- If the loop writes the dispatch record first, which is how #159 reads ("Write the dispatch record to state.json before starting the worker"), then:
  - for the first dispatch of S, the stored state is already `stage=S, attempt=1`;
  - criterion 8's `dispatched(state, S).attempt` is then 2;
  - so **the first dispatch escalates**, the opposite of criterion 8's promise.
- Cycle 1's off-by-one has flipped sign. It has not gone away.
- `factory model <n>` run by a person mid-turn has the same problem. It answers for the *next* dispatch, which is right only if that is what it says it does.

**Fix.**
- State the contract: the model is resolved from the state as it stood **before** the dispatch is recorded. Then the loop applies `dispatched` and saves.
- Put it under "Not in scope" as an obligation on #159.
- Say in criterion 9 that `factory model <n>` reports the model for the ticket's next dispatch.
- One test pins it. A state already recorded as `stage=S, attempt=1` resolves S to `complex`, because that means a second dispatch.

### R3. `allowed(role, argv)` and the global `--json`

**Evidence.**
- `--json` is a top-level flag that comes before the command (`cli.py:270`). The suite calls `main_cli(["--json", "model", "--stage", "design"])`.
- Criterion 4 matches "the leading words of argv". So `factory --json next` would not match `next`, and #222 would refuse it.
- Two honest readings of "argv" exist: the raw argv, or the words after the global options.

**Fix.**
- Define the argument as the command words after the global options. Better, have #222 pass the parsed `args.command`, plus the subcommand words.
- Test `["--json", "spec", "submit"]`.

### R4. `worker_timeout_min` and `poll_s` need values that only the maintainer can give

**Evidence.**
- Criterion 10 makes all six keys required: a missing key is exit 3. So the shipped file must carry a value for each.
- Design §6 gives values only for `attempts`, `cycles`, `wip` and `launcher`.
- `worker_timeout_min` and `poll_s` are timing constants. Under `AGENTS.md` ("a measured constant — anything timed, tuned"), a builder must stop and ask rather than pick them.
- Neither key has a reader until #159 or #220.

**Fix.** Either option works:
- The maintainer gives the two values now, and the spec records them under "Source".
- Or the two keys are optional in #218 and become required in the ticket that first reads them.

Either way, the spec should also give each key's type:
- `attempts`, `cycles`, `wip`: positive integers;
- `launcher`: the string `"herdr"`;
- `worker_timeout_min`, `poll_s`: positive numbers.

"A wrong type" is decidable only against a stated type. Also name the exception
`config.py` raises, which callers map to exit 3. #218 has no command that reads
the file, so "exit 3" can only be tested through that class.

## Notes: the plan must settle each one

**a. The split left two things with no owner.**
- **Design §10.** The build-order table still says "#218 S5: Routing v2 (v1 kept), `roles.py`, the models table". It has no row for #237, and no #237 among #159's blockers. Add it to criterion 11's `design.md` amendment.
- **`stages.md`.** The v2 table description and the radius "glob" wording (stages.md:311) were the first spec's criterion 20. #237's body names neither. Criterion 11's Supersedes notes should point the stages.md v2 description at #237 explicitly, and the one-line glob fix can stay here.

**b. `design.md` §6 must stay consistent with §2.**
- Once §2 places `document` between the proof and the review, §6's `review.md` row ("a snapshot at `proof.md`'s own commit") contradicts it.
- Either write #237's agreed definition into §6 now (the stamp is the commit that last wrote `proof.md` at snapshot time, and the loop re-proves after a Documenter turn), or mark that sentence "settled by #237".
- #186's body also claims the R9 amendment. The coordinator should note on #186 that #218 now makes it.

**c. The `[roles]` block's contract.**
- Say how a role's model is asked for. Is it a `resolve_role(table, role)`, a `factory model --role`, or #159 reading `table.by_role`?
- Say how the block is validated:
  - a key that is not a `roles.py` name is a `TableError`;
  - a role that has stages is rejected, so a role cannot have two answers;
  - say whether overrides apply to a role.

**d. Scopes and commands.**
- **`park.md`.** It is in the Builder's scope but not the Documenter's. The Documenter runs `factory park` in the ticket worktree, so `judge_paths` (#163) would fail its parking turn.
- **`**/AGENTS.md`.** It also matches `factory/AGENTS.md` (protected) and any future `.claude/AGENTS.md`. A `.claude/` write fails the loop's `hooks_disabled` check, so exclude `.claude/**`.
- **Derive the exclusions.** The Documenter's exclusions copy `merge.py`'s hard-stop list by hand (`docs/adr/**`, `docs/agents/typing.md`). Derive them from `merge.py`'s lists instead, so they cannot drift (#217's lesson). That would also catch `docs/factory/merge-policy.md`, a protected path.
- **The Planner and `park`.** Say whether the Planner is a "judge" and may `park`. Design §8 says it may.
- **`role_for` on v1-only stages.** Say what it gives for `plan` and `test`: None, or a raise.

**e. The intent no longer matches the ticket.** `intent.md` still proposes the v2
routing outcome, and lists `routing.py` and `stages.md` as the systems affected.
The final review judges against it. Add a line recording the split: the routing
outcome moved to #237, and the affected systems are now `roles.py`, `models.py`,
`config.py`, `cli.py`, the `Stage` enum, the two TOML files, `roles.md`,
`design.md` and the Supersedes notes.

**f. Until #237 lands, a v2 chain is routed by v1 rows.** `factory model <n>`
takes its stage from today's `ROWS`, which put a v2 chain at `plan`, and then
applies v2 state. No v2 chain exists before #222, so nothing is harmed. Record it
under *Could not verify*, or in the PR, so nobody reads it as v2 routing.

## Requirements to pass

- R1–R4 resolved in the criteria.
- Notes a–f answered in the spec or left explicitly to the plan.
