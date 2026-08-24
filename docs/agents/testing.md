# Tests

Every test in this repo is pytest-native. Write new tests this way, and convert any
unittest-style test you touch.

## The convention

- **Plain functions**, named `test_*`, at module level. No `TestCase` base class.
- **`@pytest.fixture`** for setup, in place of `setUp` / `setUpClass` / `tearDown`.
  Yield-fixtures cover teardown; `autouse=True` covers per-test resets of
  process-wide state.
- **Bare `assert`**. pytest rewrites it and shows both sides on failure, which is
  what `self.assertEqual` was buying.
- **Group with banner comments**, not classes. Grouping classes are legal pytest,
  but flat modules keep node IDs stable and make a test greppable by its own name.

## Translating unittest

| unittest                       | here                                                 |
| ------------------------------ | ---------------------------------------------------- |
| `self.assertEqual(a, b)`       | `assert a == b`                                       |
| `self.assertTrue(x)`           | `assert x`                                            |
| `self.assertIn(a, b)`          | `assert a in b`                                       |
| `self.assertIs(a, b)`          | `assert a is b`                                       |
| `self.assertIsNone(x)`         | `assert x is None`                                    |
| `with self.assertRaises(E):`   | `with pytest.raises(E):`                              |
| `self.fail()`                  | `pytest.fail()`                                       |
| `with self.assertLogs(lg):`    | `with caplog.at_level(level, logger=lg.name):` — then `assert caplog.records`, which is the part `assertLogs` asserts for you |
| `setUp` / `tearDown`           | a `@pytest.fixture` (yield for the teardown half)     |
| `setUpClass`                   | a `@pytest.fixture(scope="module")`                   |
| `Mock()` / `AsyncMock()`       | `mocker.Mock()` / `mocker.AsyncMock()`                |
| `with patch.object(o, "a"):`   | `mocker.patch.object(o, "a")` — no `with`; see below   |
| `m.assert_called_once_with(x)` | unchanged — `mocker` hands back the same mock objects |

**Nothing under `tests/` imports `unittest`.** Spies come from `pytest-mock`'s
`mocker` fixture: request `mocker` as a test argument and use `mocker.Mock`,
`mocker.AsyncMock`, `mocker.patch`, `mocker.patch.object`. These are the same objects
`unittest.mock` exposes — `mocker.Mock` *is* `unittest.mock.Mock` — so every
assertion you already know (`assert_called_once_with`, `call_args`, `call_count`)
works unchanged. What the fixture buys is the import boundary and automatic undo.

Two consequences worth knowing:

- **`mocker.patch*` takes no `with` block.** The patch comes off when the test ends,
  not when a block exits. If a patch must come off mid-test, that is what
  `monkeypatch` or an explicit save/restore is for.
- **A helper class that patches needs `mocker` threaded in.** `mocker` is a
  function-scoped fixture, so a scenario object driving the patched call takes it as
  an argument — see `_DispatchScenario.run` in
  `tests/test_botting/test_dispatch_time_compilation.py`.

Prefer `monkeypatch` when you only need to swap an attribute and never assert on the
call; reach for `mocker` when you need to record how something was called.

Three modules are the standing exception, and only until their own tickets land:
`test_child_process.py` and `test_inputs_helpers.py` (issue #40) and
`test_discord_comm.py` (issue #69) still import `unittest`. Each of those tickets
decides whether its module is repaired or rewritten from scratch; whatever survives
that decision is written to the convention above.

## What the scaffolding gives you

`pytest.ini` and `conftest.py` sit at the repo root — read them rather than
re-deriving what they configure. Two things there are worth knowing before you write
a test:

- **The `live` marker.** Tests that drive a real, focused game client are marked
  `@pytest.mark.live` and are excluded from a default run. Run them with
  `pytest -m live`. Anything that needs a game window belongs behind this marker.
- **The `held_movement_keys` fixture.** Constructing a `KeyboardInputWrapper` reads
  the Held-Keys Ledger, which only Main Process owns and which carries state between
  tests. Request this fixture to pin what construction sees as already held, so the
  opposite-key releases inserted at construction are a function of your test alone.

Modules that touch the Held-Keys Ledger directly reset it through an `autouse`
fixture of their own — see `tests/test_botting/test_held_keys_ledger.py`.

## Running

`pytest` from the repo root. Two modules (`test_child_process.py`,
`test_inputs_helpers.py`) currently fail to import against current source, which
interrupts collection; until that is resolved, add
`--ignore=tests/test_botting/test_child_process.py --ignore=tests/test_botting/test_inputs_helpers.py`
to get a full run.

## Changing an existing test

Preserve behaviour. A conversion is syntactic: a test that failed before must fail
after, with the same verdict. Take a per-test baseline first
(`pytest -q --tb=no -rA`), and diff it against the same run afterward.

When a test turns out to be broken, stale, or never collected, leave it that way and
file it separately. Folding a fix into a conversion hides the fix and makes the
conversion impossible to verify.
