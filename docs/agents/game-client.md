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
