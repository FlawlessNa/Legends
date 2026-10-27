"""
Reads MapleStory Classic's client files into data the bot can look up.

A top-level package, beside `botting/` and `maple/`, that imports neither of
them, nor `torch` or `ultralytics`: importing `maple` loads the detection stack,
and `game_data` has to start in well under a second.
`tests/test_game_data/test_imports.py` enforces this.

It is built in layers, and each one imports only the layers to its left:

    archive/ <- extraction/ <- catalogue/ <- report/, render/

- `archive/`: bytes to property trees. It knows nothing about the game.
- `config`: where the installed client's `Data` folder is, per machine.

The later layers arrive with their tickets (epic #259).
"""
