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

## 3. Pick or record a map

Maps live in `configs/maps/` as JSON. Two ship with the repo: `Line1Area1`
and `GhostShip1`. If one of those is where you want to farm, skip to step 4.

Otherwise, record your own. Stand your character in the map, then:

```
python toolkit/create_map.py --map YourMapName --ign YourCharacterName
```

The editor opens with three modes:

**Trail Recording** — walk your character around the map. The tool traces your
path as coloured dots (blue on platforms, green on ladders, grey mid-air).
Cover every platform and every ladder. Then, for each one: click *Set Start
Dot*, click *Set End Dot*, choose Platform or Ladder, name it, and click *Mark
as Feature*.

**Feature Selection** — draw feature boxes by hand, fine-tune what the trail
produced, and add portals (a link between two cells, one-way or bidirectional).

**Pathfinding** — once features exist, visualise the graph the bot will
actually navigate. Use it before you trust the map: if the path between two
platforms looks wrong here, it will be wrong at runtime.

*Save Edits* writes `configs/maps/YourMapName.json`.

Add `--scale 8` if the minimap is small and hard to click accurately.

Recording a map is real work, and `configs/maps/` **is** tracked — when you
finish one, commit it so nobody has to do it twice.

---

## 4. Write your profile

```
copy profiles\example.yaml profiles\yourname.yaml
```

Open it and set, at minimum:

- `ign` — your character's exact in-game name, matching your keybindings section
- `game_map` — the map file from step 3, without `.json`
- `training_skill` — your attack, which must be in your `Skill Keys`
- `included_buffs` — buffs to keep up, each also in `Skill Keys`
- `client_size` — `large` or `medium`, matching the client

The template documents every option inline, including the ones commented out.
`models_path` already points at the `global` model, which detects the character
plus five mobs; see [models.manifest.json](../models.manifest.json) if you need
a different one.

Profiles are gitignored apart from the template, so yours is yours.

---

## 5. Dry-run the map

Before letting it loose, look at what the bot thinks the map is. Open your map
in the editor's Pathfinding mode with your character standing in it:

```
python toolkit/create_map.py --map YourMapName --ign YourCharacterName
```

Confirm two things: your character is detected where it actually is, and the
computed paths between platforms look sane. If position tracking is off here,
nothing downstream will work — and this is far easier to diagnose in the editor
than by watching a bot walk into a wall.

Close the editor without saving if you changed nothing.

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

**It mistimes jumps or overshoots platforms** — the physics model doesn't know
about your gear or speed buffs. Measure the real values in the map editor
(`python toolkit/create_map.py --map <MapName> --ign <YourIGN>`), which derives
them from a recorded walk, and set `speed_multiplier` / `jump_multiplier`.
Don't guess these.

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
