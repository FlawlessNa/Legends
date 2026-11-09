# Checking work against the game client

## Probe

The probe (`python -m maple.probe`, `maple/probe.py`) looks at the open game
window and sends it a few simple inputs. It needs no Session.

**Use it** when the work depends on what is on screen: an interface region, a
menu, a minimap, a chat box. Take a screenshot, read it, and say in the PR what
you saw.

**Never use it while a Session is running.** The probe resets the Held-Keys
Ledger and sends its own keys, which would fight the bot. Nothing enforces
this: it is a rule. If you do not know whether a Session is running, ask the
maintainer.

### The window and the capture

The probe finds the one MapleStory client by its window class and executable
(`configs/game.ini` `[Client]`), never by title or IGN. With none open it exits
4; with several, 5. `--ign NAME` only picks the `configs/keybindings.ini`
section that binding names come from (`keys`, `press`); without it, the file's
only section is used.

`screenshot` and `regions` copy the screen (Desktop Duplication). The copy is
trusted only when the client is in front, before and after, did not move, and
its client area is entirely on the primary monitor. A copy that is not trusted
is asked for again for up to a second (a new process's first copy can come back
empty), then they exit 6 with the reason, and write nothing. They send no input,
so they do not bring the client to the front themselves: if the client is not
in front, ask the maintainer to bring it there.

### Elevation

`MapleStory.exe` always runs as administrator. Windows silently drops input
sent from a non-elevated process into it, with no error, so `press`, `hold`,
`write` and `click` refuse to run unless the terminal is elevated too (or the
client's token cannot be read, which means the same). They exit 2, send
nothing, and print, for example:
`Process 1234 is elevated and this one is not, so Windows would silently drop
any input. Run this terminal as administrator, then try again. Nothing was
sent.` If you see this, ask the maintainer to run the terminal as
administrator. `screenshot`, `regions` and `keys` need no elevation.

### Commands

Each prints one JSON line on stdout. Errors go to stderr with a non-zero exit
code (the module docstring lists them).

| Command                                      | Does                                                     |
| -------------------------------------------- | -------------------------------------------------------- |
| `screenshot [--region NAME \| --box l,t,r,b]` | writes a PNG to `probe/`; with no flag, the whole client |
| `regions`                                    | each region's box `[l, t, r, b]`, or null if not showing |
| `keys [--ign NAME]`                          | lists the key binding names                              |
| `press KEY [--times N] [--ign NAME]`         | keydown then keyup, N ≤ 10                               |
| `hold DIRECTION --ms MS`                     | holds a direction, then releases it, MS ≤ 10000          |
| `write TEXT`                                 | types TEXT into the chat box                             |
| `click X Y`                                  | left-clicks at pixel X, Y                                |
| `resolution WxH` / `resolution --list`       | sets the client's windowed size through Options          |

`KEY` is a binding name from `keys` (case-insensitive, such as
`"inventory menu"`) or a plain key name such as `"i"`, `"enter"` or
`"escape"`. `press` refuses directions: use `hold`. Anything unknown is refused
before any input is sent. Every command is a whole gesture that ends with every
key released.

Regions are found on screen by the `maple/screen` readers: `status_bar`, and
the strips its numbers are read from, `level`, `hp`, `mp` and `exp`;
`minimap` (expanded only); `buffs` (the row of buff icons). A region that is
not showing exits with code 3 and says why. Regions need the game data store
(`docs/agents/game-data.md`); a plain screenshot or a `--box` does not.

### Changing the resolution

```
python -m maple.probe resolution --list
python -m maple.probe resolution 800x600
python -m maple.probe resolution 1920x1080
```

Screen readers are tested on frames at several client sizes, and this sets
one without working out the Options menu again. It prints, for example,
`{"ok": true, "before": [1920, 1080], "after": [800, 600], "origin": [0, 0]}`,
where `origin` is the client area's top-left on the screen.

- **Put it back when you are done:** finish at `1920x1080`, the maintainer's
  size, and say in the PR that you did.
- Only the **windowed** sizes `--list` prints are set. A full-screen entry, a
  size the client does not list, or one bigger than the screen is refused
  (exit 2) before anything is sent.
- It presses Escape for the Game Menu (or uses it, or the Options window, if
  already open), clicks Game Option, the Graphics tab, the Resolution
  dropdown, the size's row and Confirm. Each step is found on screen from the
  client's own sprites (`maple/menus.py`), never from coordinates measured on
  one size, and checked on a fresh frame before the next.
- It succeeds only when the client's new size is the one asked for. If a step
  does not show what it should, it exits 1 naming the step and why the last
  frame did not show it, after pressing Escape until the Game Menu and the
  Options window are closed. The message ends with the client's size and
  where its client area is, for example `The client is 1920x1200, its client
  area at (0, 253), not entirely on the 2560x1440 primary monitor.`
- **It moves the window**, the only command that does: before it starts, and
  after the resize, if the client area is not entirely on the primary monitor
  but could be, it moves the window as little as it can so that it is (inside
  the work area, above the taskbar, when it fits there). A resize can leave
  the client hanging off the screen: 1920x1200 on a 2560x1440 monitor once
  ran 13 px past the bottom. It never resizes the window or brings it to the
  front this way.
- Confirm closes the Options window by itself.
- If the **Key Bindings** window is open, it refuses, since that window
  swallows Escape: close it (Cancel) first.
- It is a short scripted sequence, longer than the probe's other gestures.
  Each key and click in it is still one guarded gesture that releases every
  key.

#### At 2560x1440 the client draws everything at twice its size

Measured on the maintainer's 2560x1440 monitor (#412), with UI Size "Ideal
Ratio":

- The client stops being a window: it becomes a borderless popup at (0, 0)
  that covers the whole screen, taskbar included. Every other listed size is
  an ordinary window with a title bar.
- It draws the game and its UI at 1280x720 and doubles each pixel. The UI
  Size dropdown still says "Ideal Ratio" (its other entries are "Default
  Ratio" and "Default Ratio (Filter Applied)", not tried).
- The client's sprites match exactly on every second pixel, so `resolution`
  finds the scale on screen (1:1, else 2:1, from the status bar) and drives the
  menus on the half-size frame, doubling its clicks. Earlier it failed at
  `start` with "expected a usable frame" whenever the client was at 2560x1440.
- `screenshot` works and writes the full 2560x1440 frame. **`regions`, and
  every screen reader, read 1:1 only**, so at this size every region is
  `null`. Read the screenshot instead, or work at 1920x1080.

### Example: look at the minimap

```
python -m maple.probe regions
python -m maple.probe screenshot --region minimap
```

The second command prints, for example,
`{"ok": true, "path": "probe/2026-11-03_10-00-00-000_minimap.png", "w": 172, "h": 196}`.
Read that PNG.

### Things to know

- **Prefer a region or a box to a full-window shot.** A crop costs fewer
  tokens. Start with `regions`, and take the whole window only to find out
  where something is.
- **Coordinates are pixels in the full-window PNG**, for `--box`, the boxes
  `regions` prints, and `click` alike: the client area in physical pixels,
  with no title bar or border. Find a spot in a full-window shot, then click
  or crop there. A cropped PNG has its own origin: do not click from its
  pixels.
- **`write` needs the chat box open first.** It does not open the box itself.
  Open it with a `press` (for example `press enter`, if that opens chat in
  your client).
- `probe/` keeps the 50 most recent PNGs and is gitignored.

### In the PR

State what you checked: the exact command you ran, and the PNG path. Attach
the PNG if it helps the maintainer, since `probe/` is not committed. Say what
you did not check.

## Live Session

The probe looks at a client with no bot running. This section is for the other
case: you changed what the bot does in game, and you check it on a **Test
Session** (`CONTEXT.md`) by reading what the bot recorded. Green tests prove
Invariants, not that the bot works; this is how you find out.

**You observe, and you never steer.** During a Session you send no keys, you do
not use the probe, and you do not touch the bot. Stopping it is the only thing
you do to it. The maintainer starts it.

### The steps

1. **State the expectation in the PR, before the run.** Say what the bot should
   do and how you will count it, with numbers where you can: "on `Line1Area1`,
   `Rotation` should plan and reach about 10 targets in 3 minutes, and nearly
   every `action.finished` should be `completed`." Write it first, so the run
   can prove you wrong.
2. **Write a throwaway Bot in `scratch/`** (gitignored). It subclasses
   `MapleBot` and lists only the DecisionMakers under test, so nothing else
   acts. Add `StateSnapshot` when position matters: it records where the
   character is and where it is heading once a second, and no shipped Bot has
   it. A profile (also gitignored) names the Bot as `module:Class`, which is
   case-sensitive, for example `bot: scratch.rope_test:RopeTestBot`, and the
   module must be importable from where the maintainer launches.
3. **Ask the maintainer to start the Session**, with `--test` for sharper
   video: `python -m maple.launchers.run <profile> --test`. Give them the
   profile and the Bot file, say how long to let it run (a few minutes), and
   ask them to tell you when it is running.
4. **Read it with the Session reader**, `python -m botting.session`. Start small
   and go deeper only where the result is in doubt:
   - `summary` first: duration, the Bots and DecisionMakers, a count per Event
     Type, `action.finished` outcomes per identifier, and how it ended. A few
     hundred tokens.
   - `events --type GLOB [--where k=GLOB] [--since T] [--until T] [--limit N]`
     for the records of one kind. `--where` matches a payload field.
   - `around --at T [--window S]` for everything near one moment, such as a
     timeout.
   - `watch --until-type GLOB [--count N] --timeout S` to wait on a live
     Session.

   `T` is `+mm:ss[.s]`, plain seconds or an ISO timestamp, relative to
   `session.started`. `--json` prints one object per line. Without `DIR`, the
   newest Session under `logs/` is read.
5. **`stop`** once you have enough:
   `python -m botting.session stop --reason "enough records"`. It writes the
   stop file and waits up to 30 s for `session.ended`. The Session ends through
   `SessionManager.__exit__`, which releases every held key. `session.ended`
   says how any Session ended, in its `cause`:
   - `stop_file`: stopped through `stop`;
   - `interrupted`: Ctrl+C in its console, or a Discord kill;
   - `error`: a task or an Engine raised, and `error` names the exception
     (an Engine that dies reads `EngineFailed: Engine(<ign>) raised …`);
   - `completed`: the bots stopped on their own.

   A Session with no `session.ended` was killed hard.
6. **Pull a few `frame`s only where the result is in doubt**, after `stop`, to
   check the bot read the screen correctly: `frame --at +02:11 --box l,t,r,b`.
   It writes a PNG to `<DIR>/frames/`. Prefer a `--box` to the whole screen.
   The video can be read only once the Session has ended: on a running
   Session, `frame` fails with "… cannot be read as a video".
7. **Write the verdict in the PR**: what you expected, what the Session showed
   in counts, and the Session directory (`logs/<timestamp>/`), so the
   maintainer can read the same records. Attach a frame if one settled a doubt.
   Say what you could not verify.

### Traps

- **Always pass `--timeout` to `watch`.** Without it, `watch` waits until
  `session.ended`, and a Session killed hard never writes one, so the command
  hangs for ever. Exit codes: 0 met, 1 timeout, 2 the Session ended first.
- **Records before `session.started` have negative times.** Reach them with the
  `=` form, because argparse reads a leading `-` as a flag: `--since=-00:01`,
  not `--since -00:01`.
- **`frame --box` is in video-frame pixels**, the size of the recorded video,
  which is the tool's own definition (its `--help` says the same). On a display
  with DPI scaling this may differ from the pixels of a probe screenshot, so do
  not reuse a box from one in the other without checking the frame you get.
- **A Plan's arrival does not share its Correlation ID.** `movement.plan_started`
  and the `action.*` records of one Plan share a cid. `movement.target_reached`
  does not: it carries the cid of the cycle that *judged* arrival, which is
  usually the cycle that starts the **next** Plan (so it matches that Plan's
  `plan_started`). `CheckMobsStillSpawn` also emits `target_reached`, under its
  own cid. So never pair by cid. Pair an arrival with its Plan by
  `target_x`/`target_y` (both records carry them) and by order: the first
  `target_reached` at a Plan's target after its `plan_started`. Count only the
  Plans and arrivals of the DecisionMaker under test, and expect an arrival to
  come after the Plan's `action.finished`, not with it.
- **Every way a Plan can end is recorded.** `action.blocked`, `requeued`,
  `self_cancelled` and `cancels_other` come from the scheduler, and
  `action.finished` has the outcome `completed`, `cancelled` or `raised`. A
  count that does not add up is a finding: report it, do not round it.
- **A Session with no recording** (debug mode, recorder off) has no frames.
  `frame` exits 1 and says so.

### When the change has no records of its own

If the existing records cannot tell you whether the change worked, add an Event
Type as part of the change, and say so in the PR. The rules are in
`maple/AGENTS.md` § "Telemetry": a constant in `maple/telemetry_events.py`, a
`TypedDict` payload beside it, additive only, JSON primitives only. Emit it
with `self.emit(CONSTANT, payload)` from the DecisionMaker. Do not read the
text log for the same purpose: it is narrative, not a contract.

### Example: a Rotation change

You changed how `Rotation` picks its next target. In the PR, before the run:

> Expect on `Line1Area1`, in 3 minutes: about 10 `movement.plan_started`,
> nearly all Rotation `action.finished` as `completed`, and a
> `movement.target_reached` within 3 units of each Plan's target.

`scratch/rotation_test.py`:

```python
import maple.decision_makers as decision_makers
from maple.bots.maple_bot import MapleBot
from maple.decision_makers.state_snapshot import StateSnapshot


class RotationTestBot(MapleBot):
    def _decision_makers(self):
        return [decision_makers.Rotation, StateSnapshot]
```

and `bot: scratch.rotation_test:RotationTestBot` in a profile. You ask the
maintainer to run it with `--test` for three minutes. Then:

```
python -m botting.session summary
python -m botting.session events --type "movement.*" --limit 40
python -m botting.session events --type action.finished --where outcome=cancelled
python -m botting.session around --at +02:11
python -m botting.session stop --reason "3 minutes done"
python -m botting.session frame --at +02:11 --box 0,0,400,300
```

The verdict, in the PR (numbers invented for the example):

> Session `logs/2026-11-08_14-02-11/`, `--test`, 3:04. 14 `plan_started`; 14
> `action.finished` for Rotation (13 completed, 1 cancelled at +02:11); 13
> `target_reached`, all within 2.1 units, each paired with its Plan by target
> and order. The cancelled Plan (target 41,12) has no `target_reached` before
> the next Plan starts, and the frame shows the character mid-jump with the minimap
> read correctly, so the cancel looks like a rival Action, not a misread. Not
> verified: Sessions longer than 3 minutes, and other maps.
