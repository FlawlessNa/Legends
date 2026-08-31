# Setup

One-time install. Budget about half an hour, most of it downloads.
When you're done, go to [FIRST_BOT.md](FIRST_BOT.md).

Everything below assumes Windows and a `cmd`/PowerShell prompt at the repo root.

---

## 1. Prerequisites

### Python 3.14

The project targets **3.14** (developed against 3.14.7). Older versions will
not work with the pinned dependencies -- `numpy 2.5` and `torch 2.11` are
required for 3.14 support and dropped some of what 3.12 needed.

Get it from [python.org](https://www.python.org/downloads/release/python-3147/)
— tick **"Add python.exe to PATH"** in the installer — then confirm:

```
python --version
```

If you have several Pythons installed, use the launcher to pick this one:
`py -3.14 -m venv .venv`.

### Tesseract-OCR

Used to read the in-game chat and UI text. It is a separate program, not a pip
package.

Install the [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki),
accepting the default location. [`paths.py`](../paths.py) looks in exactly two
places:

- `%PROGRAMFILES%\Tesseract-OCR\Tesseract.exe`
- `%LOCALAPPDATA%\Programs\Tesseract-OCR\Tesseract.exe`

If it's anywhere else, `TESSERACT` silently becomes `None` and OCR fails later
with a confusing error rather than at startup. Verify with:

```
python -c "from paths import TESSERACT; print(TESSERACT)"
```

A path means you're fine. `None` means move the install or edit `paths.py`.

### GitHub CLI

Needed to download the detection models from this repo's private releases.

```
winget install GitHub.cli
gh auth login
```

---

## 2. The virtual environment

```
py -3.14 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
```

Then install dependencies. Pick one:

```
pip install -r requirements.txt        :: just running the bot
pip install -r requirements-dev.txt    :: also tests and linting -- pick this if you'll open PRs
```

Add `-r ml_training/requirements.txt` on top of either if you intend to train
your own detection models.

### GPU vs CPU

`requirements.txt` pins the **CPU** builds of `torch` and `torchvision`,
because that's what installs everywhere without special handling. It works, but
detection is the bot's hot path and CPU inference is markedly slower.

If you have an NVIDIA GPU, replace them with the CUDA 12.8 build:

```
pip uninstall -y torch torchvision
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
```

Check which one you ended up with:

```
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

`2.11.0+cu128 True` means the GPU is in play. `2.11.0+cpu False` means it
isn't -- fine to start with, worth fixing later.

CUDA 12.6 and 12.9 wheels also exist for 3.14 if 12.8 doesn't suit your driver;
substitute `cu126` or `cu129` in the index URL above.

---

## 3. Detection models

The YOLO weights aren't in git. Download the ones this commit expects:

```
python scripts/fetch_models.py
```

Each file is checked against its SHA-256 in
[models.manifest.json](../models.manifest.json) before it is put in place, so a
truncated or wrong download is a loud error rather than mysteriously bad
detection. Confirm any time with `python scripts/fetch_models.py --check`.

That manifest also documents what each model detects. `global` is the default
and covers the character plus five mobs.

---

## 4. Configuration

Three config files are personal and gitignored. Copy each template and edit it:

```
copy configs\discord.example.ini   configs\discord.ini
copy configs\keybindings.example.ini configs\keybindings.ini
copy configs\recordings.example.ini  configs\recordings.ini
```

**`discord.ini`** — every person runs their own Discord bot; nobody shares a
token. The template walks through creating one at
[discord.com/developers](https://discord.com/developers/applications). You need
the bot token, your own Discord user ID, and the name of the channel it should
report to. Enable all three Privileged Gateway Intents on the bot — the client
requests `discord.Intents.all()` and will refuse to connect without them.

**`keybindings.ini`** — one section per character, named with the character's
exact in-game name. These must mirror your *actual* in-game key layout; the bot
presses keys, it never reads the game's own bindings. Filling this in properly
is covered in [FIRST_BOT.md](FIRST_BOT.md).

**`recordings.ini`** — where session videos go. Point it at a drive with room.

### Shared config you may still need to touch

`configs/game.ini` is tracked, because it describes the *server*, not you:

```ini
[Client]
Window Titles = Dream MS
Large Client = True
```

`Window Titles` must appear in your game client's window title, or the bot will
find no clients at all. If you're on a different private server, change it —
and mention it in your PR, since it's shared. (The window *class* is separately
hardcoded to `MapleStoryClass` in `botting/utilities/client_handler.py`; the
`Class Name` key in the ini is vestigial and not read.)

---

## 5. Verify

```
python scripts/fetch_models.py --check
python -m maple.launchers.run --list
python -c "from paths import TESSERACT; print(TESSERACT)"
```

All three should print something sensible. That's enough to move on to
[FIRST_BOT.md](FIRST_BOT.md).

### About the test suite

```
pytest
```

Expect a clean run: **322 passing, 11 xfailed, 2 deselected**.

The xfails are deliberate and tracked under issue #89 -- unwritten placeholder
tests, plus a few whose expectations are machine-dependent (Tesseract's OCR
output) or of undecided correctness. They are not failures, and you should not
need to touch them. The 2 deselected are the `live` tests.

If you see anything other than a clean run on a fresh clone, that is a real
problem worth reporting rather than something to work around.

Tests behind the `live` marker drive a real, focused game client and are
deselected by default. Run them deliberately with `pytest -m live`, with the
game open.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'botting'`** — you're not at the repo
root, or the venv isn't active. Run from the root with `.venv\Scripts\activate`
done first.

**`Model 'All' ... is not on disk`** — run `python scripts/fetch_models.py`.

**No clients found / the bot can't see your character** — the game window title
doesn't contain `Window Titles` from `configs/game.ini`, or the character name
in your profile doesn't match the one in game. Name matching is fuzzy but needs
a 90% match.

**`KeyError` on a skill name at runtime** — a skill in your profile or buff list
isn't in your `keybindings.ini` `Skill Keys`, or is spelled differently from the
class definition in `maple/model/characters/`.

**Tesseract errors mentioning `tesseract_cmd`** — `TESSERACT` resolved to `None`.
See the Tesseract step above.
