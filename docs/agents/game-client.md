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

### Commands

Each prints one JSON line on stdout. Errors go to stderr with a non-zero exit
code (the module docstring lists them). Add `--ign NAME` when several clients
are open.

| Command                                      | Does                                                    |
| -------------------------------------------- | ------------------------------------------------------- |
| `screenshot [--region NAME \| --box l,t,r,b]` | writes a PNG to `probe/`; with no flag, the whole window |
| `regions`                                    | lists the regions, and which dynamic ones are showing   |
| `keys`                                       | lists the key binding names for the IGN                 |
| `press KEY [--times N]`                      | keydown then keyup, N ≤ 10                              |
| `hold DIRECTION --ms MS`                     | holds a direction, then releases it, MS ≤ 10000         |
| `write TEXT`                                 | types TEXT into the chat box                            |
| `click X Y`                                  | left-clicks at pixel X, Y                               |

`KEY` is a binding name from `keys` (case-insensitive, such as
`"inventory menu"`) or a plain key name such as `"i"`, `"enter"` or
`"escape"`. `press` refuses directions: use `hold`. Anything unknown is refused
before any input is sent. Every command is a whole gesture that ends with every
key released.

Regions: `ign`, `level`, `job`, `hp_bar`, `mp_bar`, `exp_bar`, `minimap`,
`inventory`, `chat`. A dynamic region that is not showing exits with code 3.

### Example: look at the inventory

```
python -m maple.probe press "inventory menu"
python -m maple.probe screenshot --region inventory
python -m maple.probe press "inventory menu"
```

The second command prints, for example,
`{"ok": true, "path": "probe/2026-11-03_10-00-00-000_inventory.png", "w": 412, "h": 306}`.
Read that PNG. The third command closes the inventory.

### Things to know

- **Prefer a region or a box to a full-window shot.** A crop costs fewer
  tokens. Start with `regions`, and take the whole window only to find out
  where something is.
- **Coordinates are pixels in the full-window PNG**, for `--box` and for
  `click` alike. Find a spot in a full-window shot, then click or crop there.
  A cropped PNG has its own origin: do not click from its pixels.
- **`write` needs the chat box open first.** Open it first, for example with `press enter` if that opens chat in your client. `write`
  does not open the box itself.
- `probe/` keeps the 50 most recent PNGs and is gitignored.

### In the PR

State what you checked: the exact command you ran, and the PNG path. Attach
the PNG if it helps the maintainer, since `probe/` is not committed. Say what
you did not check.
