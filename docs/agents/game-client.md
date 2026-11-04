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
trusted only when the client is in front, before and after, and did not move.
Otherwise they exit 6 with the reason, and write nothing. They send no input, so
they do not bring the client to the front themselves: if the client is not in
front, ask the maintainer to bring it there.

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
`{"ok": true, "before": [1920, 1080], "after": [800, 600]}`.

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
  does not show what it should, it exits 1 naming the step, after pressing
  Escape until the Game Menu and the Options window are closed.
- If the **Key Bindings** window is open, it refuses, since that window
  swallows Escape: close it (Cancel) first.
- It is a short scripted sequence, longer than the probe's other gestures.
  Each key and click in it is still one guarded gesture that releases every
  key.

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
