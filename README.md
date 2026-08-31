# Legends

A MapleStory botting framework for private servers. It drives one or more game
clients directly — reading the screen with YOLO detection models and OCR,
pathfinding over the minimap, and sending synthetic input — while reporting to
you over Discord.

**Windows only.** The bot talks to the game through Win32 window handles and
raw input; there is no macOS or Linux path.

> Automation violates the terms of service of essentially every MapleStory
> server. This exists for the private-server tinkering it was built for. Whether
> you run it, and where, is on you.

## Getting started

Three documents, in order:

1. **[docs/SETUP.md](docs/SETUP.md)** — install Python 3.14, the dependencies,
   Tesseract, and the detection models. Do this once.
2. **[docs/FIRST_BOT.md](docs/FIRST_BOT.md)** — configure your keys, record a
   map, write a profile, and get a character farming.
3. **[CONTRIBUTING.md](CONTRIBUTING.md)** — branching, tests, and how to open a
   pull request.

The short version, once setup is done:

```
copy profiles\example.yaml profiles\yourname.yaml
notepad profiles\yourname.yaml
python -m maple.launchers.run yourname
```

## How the pieces fit

| Directory | What it is |
| --- | --- |
| `botting/` | The game-agnostic engine: process orchestration, input control, screen capture, Discord comms, logging. Knows nothing about MapleStory. |
| `maple/` | The game-specific layer built on top: character models, minimap navigation, movement compilation, and the `DecisionMaker`s that choose what to do. |
| `ml_training/` | The pipeline for building your own detection models — capture, annotate, train, version, promote. Only needed if the published models don't cover your mobs. See [ml_training/README.md](ml_training/README.md). |
| `toolkit/` | Standalone scripts: map recording, dataset inspection, movement calibration, profiling. |
| `scripts/` | Repo maintenance — currently model download and publication. |
| `configs/` | Shared configuration, plus templates for the personal files. |
| `profiles/` | Your per-character launch settings. Gitignored except the template. |
| `tests/` | pytest suite. `pytest -m "not live"` runs everything that doesn't need the game open. |

A run is a **Session**: `SessionManager` spawns an `Engine` per group of bots
plus a peripherals process for Discord and screen recording, and each bot's
`DecisionMaker`s take turns deciding what that character does next.

![Process topology of the engine](docs/img/engine-topology.svg)

Four kinds of process, and one rule that shapes the rest: **only Main Process
may press a key.** Engines read the game clients and decide what to do; they
send an `ActionRequest` to Main Process, which arbitrates by priority and sends
the input itself. [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) follows that path
end to end, plus the three others — Discord control, logging and telemetry, and
cross-process shared state.

[CONTEXT.md](CONTEXT.md) defines the vocabulary the codebase uses — read it
before naming anything new.

## What lives where, and why

Two categories of file are deliberately **not** in git:

**Model weights.** `data/` is ignored entirely. The detection models are
published as GitHub Release assets and pinned by
[models.manifest.json](models.manifest.json):

```
python scripts/fetch_models.py           # download what this commit expects
python scripts/fetch_models.py --check   # verify what you have
```

They stay out of git because `.pt` files don't delta-compress, so every retrain
would weld another 6 MB into history permanently. Everything else under `data/`
— datasets, capture runs, training runs — is local scratch worth about 2 GB and
is nobody else's business.

**Personal configuration.** `configs/discord.ini`, `configs/keybindings.ini`,
`configs/recordings.ini` and `profiles/*.yaml` are yours. Each has a committed
`.example` template beside it.

Everything else under `configs/` **is** tracked and shared — most importantly
`configs/maps/`, which holds the recorded minimap layouts. Those take real
effort to produce, so when you record a new map, commit it.

## Documentation

| | |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the engine works — processes, the action path, control, logging, shared state. |
| [CONTEXT.md](CONTEXT.md) | Domain vocabulary. The words the code uses and the synonyms it avoids. |
| [docs/adr/](docs/adr/) | Architecture decision records — why things are the way they are. |
| [docs/agents/](docs/agents/) | Conventions for AI agents working in this repo. |
| [docs/planning/](docs/planning/) | Design notes and the archived legacy backlog. |
