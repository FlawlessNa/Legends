# Your first bot

Assumes you've finished [SETUP.md](SETUP.md). By the end of this you'll have a
character farming a map on its own.

Work through it in order — each step is checkable on its own, which matters
because when something is wrong at step 5 the cause is almost always step 2.

---

## 1. Get the client seen

Start the game, log your character in, and leave the window open. Then:

```
python -c "from maple.screen.client import find_client; print(find_client())"
```

A window handle means the bot can find your client.

`WindowNotFound` means no visible window has the `Class Name` from
`configs/game.ini` *and* belongs to a process named `Executable`
(`MapleStory.exe`). The title isn't read. Check the executable's name in Task
Manager and update the ini if it differs — that file is tracked and shared, so
say so in your PR. `MultipleWindows` means more than one client is open; the
bot drives exactly one.

---

## 2. Bind your keys

This is the step people get wrong, and it fails late and confusingly — usually
as a `KeyError` on a skill name once the bot is already running.

Copy the template if you haven't:

```
copy configs\keybindings.example.ini configs\keybindings.ini
```

Then edit it. Rename the `[YourCharacterName]` section to your character's
**exact** in-game name, and fill in the three dicts:

- **`Non Skill Keys`** — jump, pet food, the menu toggles, chat toggle.
- **`Skill Keys`** — every skill the bot will cast: your attack, your buffs,
  teleport, door. Names must match the skill definitions for your class in
  `maple/model/characters/` (`magicians.py`, `thiefs.py`). A skill you don't
  list simply can't be used.
- **`Quick slots`** — where your potions and pet food sit in the in-game
  quick-slot bar, numbered `[1,2,3,4]` on the top row and `[5,6,7,8]` below.

Two rules worth repeating: the values are **Python dict literals** read with
`eval()`, so the quoting and commas matter; and they must mirror your **actual
in-game binds**, because the bot presses keys blind — it never reads the game's
own configuration.

Check it loads:

```
python -c "from botting.controller import key_binds; print(key_binds('YourCharacterName'))"
```

You should get one flat dict with every key you listed.

---

## 3. Extract the game data and pick a map

The bot reads every map's platforms, ropes and portals from the client's own
files, through `game_data/`. There is no map file to record. Extract the
installed client once (and again after a patch):

```
copy configs\game_data.example.ini configs\game_data.ini
python -m game_data extract
```

Set the client's `Data` folder in `configs/game_data.ini` first;
[docs/agents/game-data.md](agents/game-data.md) has the details. Then find the
game's name for the map you want to farm:

```
python -m game_data search Ellinia --kind map
```

A map is named `street: map name`, such as `"Victoria Road: Ellinia"`. Its id
works too.

---

## 4. Write your profile

```
copy profiles\example.yaml profiles\yourname.yaml
```

Open it and set, at minimum:

- `ign` — your character's exact in-game name, matching your keybindings section
- `map` — the game's name for your map from step 3
  (`"Victoria Road: Ellinia"`), its id, or `auto` to have the bot read it off
  the minimap at start
- `mobs` — the mobs to attack, by the detection model's class names (see
  [models.manifest.json](../models.manifest.json)), e.g. `[Bubbling]`. With
  none, the bot detects no mobs and never casts its training skill
- `training_skill` — your attack, which must be in your `Skill Keys`
- `included_buffs` — buffs to keep up, each also in `Skill Keys`
- `client_size` — `large` or `medium`, matching the client

The template documents every option inline, including the ones commented out.
`models_path` already points at the `global` model, which detects the character
plus five mobs; see [models.manifest.json](../models.manifest.json) if you need
a different one.

Profiles are gitignored apart from the template, so yours is yours.

---

## 5. Check the position read

Before letting it loose, check that the bot can place your character on the
map. With your character standing in it, run the position check beside the
client. It sends no keys:

```
python -m toolkit.position_check live --map "Victoria Road: Ellinia"
```

Walk around (by hand) and confirm the fused position follows your character and
is rarely `UNSURE`. If position reading is off here, nothing downstream will
work, and it is far easier to diagnose here than by watching a bot walk into a
wall.

---

## 6. Run it

```
python -m maple.launchers.run yourname
```

The bot takes over the client, so leave the window alone. Watch the console for
the first minute — it logs what each `DecisionMaker` chooses and why.

If you configured Discord, your bot posts to its channel when the session comes
up and reports failsafes as they trigger.

Logs land in `logs/`, one directory per Session.

---

## Tuning it

Once it runs at all, these are the dials worth turning, roughly in order:

**It attacks too rarely or too eagerly** — `mob_count_threshold` is the minimum
mobs on screen before the attack is worth casting.

**It mistimes jumps or overshoots platforms** — set `speed_multiplier` /
`jump_multiplier` to your character's real speed and jump stats (the ability
window shows them). What is still off after that is a Calibration constant
(`calibration:` in the profile), measured by a Trial schedule
(`configs/trials/`, `bot: calibration`). Don't guess these.

A calibration profile is short: `ign`, `bot: calibration`, and under `settings`
the `map`, your `character_class` (the skill table decides whether Plans may
Teleport; `Swordsman` has none) and `trial_schedule`. It has no `models_path`,
because the bot detects no mobs. It needs `configs/recordings.ini` (copy
`recordings.example.ini`), and runs without `configs/discord.ini`. The Session
ends when the schedule has finished. See `maple/bots/calibration.py`.

**It doesn't notice it's stuck** — `mob_spawn_alert_timer` and
`mob_spawn_alert_threshold` control the "no mobs are spawning" alert, which is
usually the first sign the bot is wedged or someone took the map.

**It can't find your character reliably** — `detection_configs` names a section
in `configs/character_detection.ini`, each describing a different visual cue
(a cape colour, a podium effect). Pick the one matching your character's look,
or add a section for it.

**Detection is poor on your mobs** — the shipped models cover a fixed set. To
train your own, see [ml_training/README.md](../ml_training/README.md), then
publish the result with `python scripts/publish_models.py` so everyone else
gets it too.
