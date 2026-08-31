# Setup

One-time install. Budget about half an hour, most of it downloads.
When you're done, go to [FIRST_BOT.md](FIRST_BOT.md).

Everything below assumes Windows and a `cmd`/PowerShell prompt at the repo root.

---

## 1. Prerequisites

### Python 3.12

The project is developed against **3.12** (3.12.4 specifically) and is not
tested on anything else. 3.13 in particular is likely to fight you over
`torch` and `PyQt6` wheels.

Get it from [python.org](https://www.python.org/downloads/release/python-3129/)
— tick **"Add python.exe to PATH"** in the installer — then confirm:

```
python --version
```

If you have several Pythons installed, use the launcher to pick this one:
`py -3.12 -m venv venv`.

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
py -3.12 -m venv venv
venv\Scripts\activate
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

If you have an NVIDIA GPU, replace them with the CUDA 12.4 build:

```
pip uninstall -y torch torchvision
pip install torch==2.4.1 torchvision==0.19.1 --index-url https://download.pytorch.org/whl/cu124
```

Check which one you ended up with:

```
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
```

`2.4.1+cu124 True` means the GPU is in play. `2.4.1+cpu False` means it isn't —
fine to start with, worth fixing later.

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

`pytest` does not currently come back green, and that is a known state rather
than something you broke. Run it like this:

```
pytest --ignore=tests/test_botting/test_child_process.py --ignore=tests/test_botting/test_inputs_helpers.py
```

Expect roughly **261 passing, 11 failing, 8 errors**. The failures break down as:

- **Two modules interrupt collection** (`test_child_process.py`,
  `test_inputs_helpers.py`) — they import names that have since moved. Tracked
  as issues #40 and #69; `--ignore` them, as above.
- **Eight `pytest.fail()` stubs** in `test_controller.py` and
  `test_screenshots.py` — deliberate placeholders for tests nobody has written.
- **Eight errors in `test_minimap.py`** — the module loads fixtures by relative
  path (`images/test_minimap1.png`), so it only passes with `tests/` as the
  working directory.
- **Three genuine failures**: `test_box.py::test___getitem__`,
  `test_chat_lines.py::test_read_text`, and
  `test_ml_training.py::test_all_required_files_exist` (which asserts on a
  `dataset_manager/augmentation.py` that doesn't exist).

Before you open a pull request, take that baseline first and compare against it
afterwards — the bar is "no *new* failures", not a clean run. See
[CONTRIBUTING.md](../CONTRIBUTING.md).

Tests behind the `live` marker drive a real, focused game client and are
deselected by default. Run them deliberately with `pytest -m live`, with the
game open.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'botting'`** — you're not at the repo
root, or the venv isn't active. Run from the root with `venv\Scripts\activate`
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
