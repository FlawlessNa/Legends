@AGENTS.md

## Claude Code

The instructions above come from `AGENTS.md`, which every agent in this repo
shares. Put project guidance there, not here — this file is for Claude-specific
behaviour only.

`botting/`, `maple/`, and `tests/` each hold an `AGENTS.md` plus a one-line
`CLAUDE.md` that imports it. Those `CLAUDE.md` files are shims: edit the
`AGENTS.md` beside them instead. Claude loads a nested file when it reads a file
in that directory, so package rules arrive on demand rather than at launch.
