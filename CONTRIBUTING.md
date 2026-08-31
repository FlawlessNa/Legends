# Contributing

This repo went from one person to several. Most of what follows exists so that
"it works on my machine" stays true on everyone else's.

New here? Start with [docs/SETUP.md](docs/SETUP.md), then
[docs/FIRST_BOT.md](docs/FIRST_BOT.md). This document is about changing the
code, not running it.

---

## Branching

`dev` is the default branch and what pull requests target. There is no `main`.

Branch from `dev`, name it for what it does (`fix/rope-jump-release`,
`feat/party-rebuff-zone`), and open a PR when it's ready. Direct pushes to `dev`
are for trivia only; anything touching the engine, movement, or decision-making
should go through a PR so someone else sees it.

---

## Before you open a PR

**Take a test baseline first.** The suite is not green — see
[docs/SETUP.md](docs/SETUP.md#about-the-test-suite) for exactly which failures
are expected and why. The bar is **no new failures**, not a clean run:

```
pytest --ignore=tests/test_botting/test_child_process.py --ignore=tests/test_botting/test_inputs_helpers.py -q --tb=no -rA
```

Run that on `dev` before you start, keep the output, and diff it against the
same command on your branch.

Tests behind the `live` marker drive a real, focused game client. They're
deselected by default; run them with `pytest -m live` and the game open if you
touched input, movement, or detection.

**Lint what you changed.**

```
ruff check botting maple ml_training tests toolkit conftest.py paths.py
ruff format --check <the files you touched>
```

The codebase is not fully formatted yet, so don't run `ruff format` across
everything — that buries your change in a reformat diff.

---

## Writing tests

`tests/AGENTS.md` and `docs/agents/testing.md` are the full convention. The
short version:

- pytest-native, always: module-level `test_*` functions, `@pytest.fixture`
  instead of `setUp`/`tearDown`, bare `assert`. No `TestCase`; spies come from
  `pytest-mock`'s `mocker`.
- Anything needing a game window goes behind `@pytest.mark.live`.
- Converting an old test preserves its behaviour. If you find one that's
  broken or stale, leave it and file it — don't fold a fix into an unrelated PR.

---

## Naming things

[CONTEXT.md](CONTEXT.md) is the project's glossary: what a Session is, what a
Correlation ID covers, what a Log Bucket is — and, for each, the synonyms it
deliberately avoids. Use its vocabulary in code, tests, commit messages, and
issue titles.

If the concept you need isn't there, that's a signal: either you're inventing
language the project doesn't use, or there's a genuine gap worth adding.

Decisions with lasting consequences go in [docs/adr/](docs/adr/) as an ADR. If
your change contradicts an existing one, say so explicitly in the PR rather
than quietly overriding it.

---

## Issues

Issues live in GitHub Issues on `FlawlessNa/Legends`; `gh` is the expected
interface. Conventions are in [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md),
and the triage label vocabulary (`needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`) is in
[docs/agents/triage-labels.md](docs/agents/triage-labels.md).

`docs/planning/legacy-backlog.md` is an archive of old TODO lists. It is
**out of date** and is not a work queue — don't pick things off it without
checking them against the current code first.

---

## Things that need care

**Never commit `configs/discord.ini`.** It holds a live bot token. It's
gitignored, and everyone runs their own bot, so there's no reason for it to be
shared. Same for `configs/keybindings.ini`, `configs/recordings.ini`, and your
`profiles/*.yaml`.

**Do commit `configs/maps/`.** Recorded maps are shared work and expensive to
reproduce. When you record one, it belongs in a PR.

**`configs/game.ini` and `configs/character_detection.ini` are shared.**
Changing them changes everyone's setup — call it out in the PR description.

**Model weights don't go in git.** `.pt` files don't delta-compress, so each one
committed is permanently welded into history. To publish new weights:

```
python scripts/publish_models.py --dry-run   # check the plan
python scripts/publish_models.py             # upload + re-pin the manifest
```

Then commit the updated `models.manifest.json` — that commit is what tells
everyone else to run `python scripts/fetch_models.py`.

**Don't put per-user settings in tracked source.** Character names, maps, and
skill choices belong in `profiles/*.yaml`. That's the whole reason the launcher
scripts were replaced with `python -m maple.launchers.run <profile>`.

---

## Working with AI agents

`AGENTS.md` at the root and in `botting/`, `maple/`, and `tests/` carry the
repo's conventions for agents; `CLAUDE.md` files are thin shims that import
them. Put project guidance in `AGENTS.md`, not `CLAUDE.md`.
