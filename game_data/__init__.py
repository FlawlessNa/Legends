"""
Reads MapleStory Classic's client files into data the bot can look up.

A top-level package, beside `botting/` and `maple/`, that imports neither of
them, nor `torch` or `ultralytics`: importing `maple` loads the detection stack,
and `game_data` has to start in well under a second.
`tests/test_game_data/test_imports.py` enforces this.

It is built in layers, and each one imports only the layers to its left:

    archive/ <- extraction/ <- catalogue/ <- report/, render/

- `archive/`: bytes to property trees. It knows nothing about the game.
- `extraction/`: the installed client into a store of Extractions, losslessly,
  with every canvas as a PNG. It knows nothing about the game either.
- `catalogue/`: an Extraction's typed tables, built from its raw layer alone,
  and the lookups over them: maps by name or ID, so far.
- `config`: where the installed client's `Data` folder is, per machine, and
  where the store is by default.
- `cli`: `python -m game_data`, and the only module that prints.

`docs/agents/game-data.md` covers the commands, the lookups and the store.

`report/` and `render/` arrive with their tickets (epic #259).
"""
