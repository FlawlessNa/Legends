# Assessment: movement framework, unit testing, logging (2026-08-19)

Shared context for three wayfinder charting sessions. Source: code exploration of the
`new-map-system-cherry-pick` branch. Each workstream gets its own wayfinder map;
cross-map ownership of shared decisions is listed at the bottom.

## Architecture facts (verified in code)

The movement pipeline is a near-pure chain in `MovementHandler`
(`maple/model/mechanics/movement_mechanics_v2.py`):

```
compute_path → path_into_movements → movements_into_action → KeyboardInputWrapper → .send()
```

Only `.send()` touches the game — **except** for one hidden impurity:
`KeyboardInputWrapper.__post_init__` (`botting/controller/inputs/focused_inputs.py:142`)
and the action builders (`maple/actions/movements_v2.py:69,117,224`) query live Win32
keyboard state via `get_held_movement_keys(handle)`. Injecting initial held-keys as a
parameter (defaulting to the OS query) makes the whole pipeline
`(map config, start, end, params) → keystroke timeline`, fully deterministic offline.
This is the **held-keys seam refactor** — the prerequisite for both offline movement
testing and unit tests.

## Known hazards (pre-existing, hide bugs)

- `movement_mechanics_v2.py:341` — `except Exception: breakpoint()` swallows all errors
  in `movements_into_action`, silently returns `None`.
- `breakpoint()` at lines 171 and 322; unreachable code after `raise` at 146.
- `DEBUG = True` module constant with `cv2.imshow` in the production path.
- `@lru_cache` on instance methods keeps `self` alive and never invalidates on
  minimap/grid edits.

## Workstream 1 — movement testing/tuning/calibration framework

Three layers, cheapest first:

- **Layer A, offline movement lab** (no game): after the seam refactor, sample
  (start, end) pairs per map JSON; assert path exists; compile to movements and input
  structure; check invariants (no key left held except `forced_key_releases`, no
  opposite keys held simultaneously, duration consistent with `grid.speed`). Golden
  snapshot tests of keystroke timelines for fixed scenarios.
  `tests/test_maple/test_minimap_mechanics.py` already sketches this idea (10k path
  simulations) but is empty.
- **Layer B, calibration CLI** (game running, scripted): execute one primitive at a
  time (walk N px, single jump, teleport), measure minimap position before/after,
  fit real constants. Tuning constants currently scattered/guessed: `FIRST_DELAY=0.5`,
  hard-coded `0.75` jump airtime (`movements_v2.py:116`), `_FALL_LEN_EXT=3`,
  `_NARROW_PLATFORM_THRESHOLD=5`, `grid.speed`. Fitted values should live in
  per-character JSON config, not code.
- **Layer C, live telemetry**: one structured JSONL record per action (start pos,
  target, path, movements, predicted vs actual end pos, cancelled?). Offline analyzer
  finds which movement types diverge. Format owned by the logging map.

## Workstream 2 — unit testing strategy

Test where the branch's change risk is: the maple model layer, not botting/ infra.
Priority order:

1. `KeyboardInputWrapper` (append/insert/fill/truncate/keys_held, opposite-key
   clearing) — pure after seam refactor, everything depends on it.
2. `movements_v2` primitives — table-driven key/event/delay assertions.
3. `path_into_movements` — hand-built tiny grids with known expected movement
   sequences; pin down which node transitions are legal (the `match` branches).
4. Property-based (hypothesis) path sweep over real map configs: random start/end →
   path exists, movements compile, invariants hold.
5. Minimap creation model: JSON config → grid snapshot tests.

botting/ infra (engine, async task manager, multiprocess): keep existing
`tests/test_botting` running; defer new coverage to one integration smoke test with
fakes. Setup: pytest, conftest fixture patching `get_held_movement_keys`,
`@pytest.mark.live` marker for game-window tests, excluded by default.

## Workstream 3 — logging strategy

Current state (`botting/__init__.py`): single root logger, one rotating file per day,
console at INFO; per-module `LOG_LEVEL` constants used as manual verbosity throttles
(conflates level with topic). Child processes share handlers via
`botting/utilities/child_process.py`.

Direction:

- Replace `LOG_LEVEL` constants with `logging.config.dictConfig` from a config file;
  logger names are already hierarchical, so per-subsystem levels are config entries.
- Split handlers by subsystem (movement/pathing, decisions/engine, catch-all);
  per-run timestamped log directory.
- Separate diagnostics from narrative: "what did the bot decide and why" moves to the
  JSONL telemetry stream (one record per decision/action, correlation `action_id`);
  text logs keep warnings/errors/lifecycle only.
- Cheap wins: lazy `%s` formatting; consider QueueHandler/QueueListener for child
  processes.

## Cross-map ownership (avoid double-deciding)

- **Held-keys seam refactor** → owned by the *movement framework* map; the unit-testing
  map depends on it, doesn't re-decide it.
- **JSONL telemetry format/transport** → owned by the *logging* map; the movement
  framework map (Layer C) consumes it.
- Each map's Notes section should link the other two maps.
