# The merge policy

**CI decides what merges. No agent does, and Nassim does not have to.**

A workflow evaluates this policy on every PR and merges when **every** condition
holds. Anything failing any condition waits for a person. **The default is to
wait.** An agent cannot merge its own work, because an agent cannot merge at
all — and a permission granted in conversation never reaches the next agent, so
it is not a mechanism. **[mechanical]** once the workflow is on the default
branch and #151's checks exist; until then nothing merges. See
[What is live today](#what-is-live-today).

This is `auto_merge_types` (#160) at its first notch. It widens only by editing
`factory/merge.py` — which this policy never merges by itself — so `git log`
answers "when did we start trusting this, and who decided".

## Where it lives

| What | Where |
| --- | --- |
| The values | `POLICY` in `factory/merge.py` — the only place they are held |
| The evaluation | `evaluate()` in the same module, a pure function of the PR's facts |
| The workflow | `.github/workflows/merge-policy.yml`, which carries no condition of its own |
| Locally | `factory merge check <pr>` — the same command CI runs, the same answer |

This page states the policy; the module decides it. A test fails if a condition
or a value below goes missing from this page.

## The conditions

Each has a name, which is what a report calls it. **Exit 3** means a person must
settle it; **exit 1** means the PR's author can fix it and re-run. When both
kinds fail, 3 wins.

| # | Condition | Holds when | Fails with |
| --- | --- | --- | --- |
| 1 | `closes-one-ticket` | The PR body closes exactly one ticket, an open issue in this repository | 1 |
| 2 | `ticket-type` | Every `type:` label on the ticket is `type:chore` or `type:refactor`, and there is one | 3 |
| 3 | `ticket-method` | The ticket's only `method:` label is `method:suite` | 3 |
| 4 | `paths-allowed` | Every path in the diff matches `factory/**`, `docs/**`, `.claude/**` or `tests/test_factory/**` | 3 |
| 5 | `no-hard-stop` | No path is on the hard-stop list, **whatever the allowlist says** | 3 |
| 6 | `checks-green` | `suite`, `ruff-check`, `ruff-format` and `pyright` each succeeded on the head commit, posted by `github-actions` | 1 if pending or red; 3 if one never reported |
| 7 | `could-not-verify` | The PR body's "Could not verify" section is present and says something | 1 |
| 8 | `working-branch` | The base is `movements-improvements` — never `dev`, never `main` | 3 |

Conditions 1–8 are the issue's (#194). Three more were added when the spec was
reviewed, each closing a way the eight could be satisfied while defeating them:

| Condition | Holds when | Fails with | Why |
| --- | --- | --- | --- |
| `not-self-change` | No path is in the protected set below | 3 | Otherwise a `type:chore` PR could widen the allowlist, or change the dispatcher to return 0, and merge itself |
| `same-repository` | The head branch is in this repository, not a fork | 3 | The repository is public; a fork's author has no push access and no say |
| `not-draft` | The PR is not a draft | 1 | A draft is by its own declaration not finished |

### Why these paths and not others

`factory/`, `docs/`, `.claude/` and `tests/test_factory/` are the factory's own
plumbing. Nothing in `botting/` or `maple/` imports them, so a wrong merge costs
a revert and cannot reach the bot.

**`.factory/**` is not on the list**, and every factory PR touches
`.factory/<n>/`. So, read as written, **no ticket PR auto-merges yet.** Adding
it is a widening of trust, which is the maintainer's to decide, not an agent's;
it is one line in `POLICY.allowed_paths`.

### The hard-stop list

`AGENTS.md` → What you may change, as globs. Checked independently of the
allowlist, so widening one can never relax the other.

| Glob | `AGENTS.md` item |
| --- | --- |
| `botting/controller/**` | Input send path, focus handling, Held-Keys Ledger (ADR 0002) |
| `maple/model/mechanics/movement_mechanics_v2.py` | Dispatch-time compilation (ADR 0002) |
| `botting/__init__.py`, `botting/logging_config.py`, `botting/telemetry.py` | Telemetry envelope and transport (ADR 0001) |
| `docs/adr/**`, `docs/agents/typing.md` | Anything an ADR decides (ADR 0003's ratchet mechanics) |
| `configs/maps/**` | Map JSON |
| `**/requirements*.txt`, `pyproject.toml`, `.pre-commit-config.yaml` | Pinned dependency versions, hook revisions included |
| `maple/decision_makers/inventory_manager.py` | Parked |

`AGENTS.md` is prose, so this list can drift from it. A new ADR, or a new
hard-stop item, must be added here and in `POLICY.hard_stop_paths` by hand until
a machine-readable list exists (#143).

### The protected set

The policy never merges a change to itself, or to anything its verdict depends
on:

- `docs/factory/merge-policy.md`, `tests/test_factory/test_merge.py`,
  `.github/**`
- Every module the `factory` console script imports, transitively:
  `factory/__init__.py`, `factory/__main__.py`, `factory/chain.py`,
  `factory/cli.py`, `factory/exit_codes.py`, `factory/hooks.py`,
  `factory/merge.py`

The second list is computed by a test, not trusted: a new import fails the
suite until a person adds it here. The cost is real — most factory tickets touch
`factory/cli.py`, so they wait.

## Definitions

- **Closing reference.** After HTML comments are stripped, `close`, `closes`,
  `closed`, `fix`, `fixes`, `fixed`, `resolve`, `resolves` or `resolved`, any
  case, an optional colon, then `#<n>`, `<owner>/<repo>#<n>`, or an issue URL.
  Parsed from the body because GitHub links nothing for a PR whose base is not
  the default branch.
- **"Says something".** The section runs from a heading starting "Could not
  verify" to the next heading of its level. After HTML comments are stripped it
  must contain a word character and not be just `n/a`, `none` or `tbd`.
- **Paths.** Every path the diff touches, **including the old path of a
  rename**, read from the paginated REST endpoint. If fewer paths are read than
  the PR says it changed, nothing is judged.
- **Globs** are anchored at the repository root and case-sensitive; `*` stays
  within one directory, `**` crosses them.
- **A check** counts only as its most recent run on the head commit, only from
  the `github-actions` app, and is green only on `success`.

## What CI does

1. On a PR being opened, edited, reopened, pushed to or marked ready, and when
   #151's `CI` workflow completes, it finds the PR and its base branch.
2. It checks out **the base branch** — never the PR — and runs
   `factory --json merge check <pr>`.
3. Exit 0: it re-reads the PR, and merges only if the base and head are what was
   evaluated, pinned with `--match-head-commit`. A merge commit, not a squash.
4. Anything else: the verdict goes to the job summary and the job passes —
   **waiting is not a failure.** If GitHub could not be read (`readable:
   false`), the job **fails**, so a broken gatherer is seen.

To turn it off: `gh workflow disable "Merge policy"`. To turn it down: edit
`POLICY`, which waits for a person like any change to the policy.

## What is live today

Three things stand between this page and the first auto-merge, all deliberate:

1. **The workflow runs from the default branch (`dev`).** GitHub reads
   `pull_request_target` and `workflow_run` workflows from the default branch
   only. Until this file reaches `dev`, it never fires.
2. **No workflow posts the required checks yet.** #151 owns them, from a
   workflow named `CI`, with jobs named `suite`, `ruff-check`, `ruff-format`
   and `pyright`. Until then `checks-green` fails for every PR.
3. **`.factory/**` is not allowlisted**, as above.

Until all three change, `factory merge check` is still the way to see what CI
would decide.
