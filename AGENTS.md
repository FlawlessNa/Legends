# Legends — agent instructions

Read this, then read **only** the doc your work needs. Guidance stays
tool-neutral: `AGENTS.md` here and in each package is read by every agent,
and there are no `CLAUDE.md` files (see `docs/SETUP.md`).

**Two rules, everywhere:**

- **You never merge into `dev`.** The maintainer does.
- **Say what you could not verify.** Green tests prove Invariants, not that the
  bot works. If your change could alter which keys reach the game, or when, say
  so.

## What are you doing?

| You are…                                  | Read                                                   |
| ----------------------------------------- | ------------------------------------------------------ |
| Discussing a topic, intent or spec        | `docs/agents/topics.md` (start with `/intent`)         |
| Working a ticket, or any code change      | `docs/agents/tickets.md`                               |
| Running an epic's tickets with agents     | `docs/agents/orchestrating.md` (`/orchestrate`)        |
| Writing or changing tests                 | `docs/agents/testing.md`                               |
| Hitting a Ruff or Pyright error           | `docs/agents/typing.md`                                |
| Reviewing a PR                            | `docs/agents/code-review.md`                           |
| Filing, labelling or reading issues       | `docs/agents/issue-tracker.md`, `triage-labels.md`     |
| Tracing how a decision becomes a keypress | `docs/agents/engine-architecture.md`                   |
| Extracting or reading the client's data   | `docs/agents/game-data.md`                             |

## The repo

- `botting/`: the generic engine (processes, input, logging, telemetry). It
  knows nothing about MapleStory.
- `maple/`: the game layer built on it (movement, decisions, minimap,
  interface reading).
- `game_data/`: reads the MapleStory Classic client's files into game data. It
  imports neither `maple` nor `botting`.
- `tests/`: the pytest suite. Opt-in markers `live`, `system`, `lab` and
  `client_files` are deselected by default (`docs/agents/testing.md`).
  `configs/`: `.ini` settings, plus one JSON per map under `configs/maps/`.
- `toolkit/`: standalone scripts that nothing imports. `ml_training/`: model
  training.
- `docs/adr/`: architecture decisions. Contradicting one is allowed; doing it
  silently is not.

`maple` imports `botting`, never the reverse. `botting/`, `maple/` and `tests/`
each have an `AGENTS.md` with rules for that package.

**Vocabulary:** `CONTEXT.md` is the domain glossary. Use its terms, and avoid
the synonyms it rejects (`docs/agents/domain.md`).
