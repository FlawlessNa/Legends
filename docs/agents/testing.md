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

There are no longer any exceptions. The last three fell with issues #40 and #69:
`test_child_process.py` and `test_discord_comm.py` were deleted as dead, and
`test_inputs_helpers.py` was repointed at the symbols' current home and converted.

## What the scaffolding gives you

`pytest.ini` and `conftest.py` sit at the repo root — read them rather than
re-deriving what they configure. Two things there are worth knowing before you write
a test:

- **Two opt-in markers.** `@pytest.mark.live` is for tests that drive a real,
  focused game client; `@pytest.mark.system` is for tests that mutate
  machine-global state, such as the keyboard layouts loaded on the machine. Both
  are excluded from a default run — `pytest -m live`, `pytest -m system`.
  Anything needing a game window, or leaving a trace outside the test process,
  belongs behind one of them.
- **The `held_movement_keys` fixture.** Constructing a `KeyboardInputWrapper` reads
  the Held-Keys Ledger, which only Main Process owns and which carries state between
  tests. Request this fixture to pin what construction sees as already held, so the
  opposite-key releases inserted at construction are a function of your test alone.

Modules that touch the Held-Keys Ledger directly reset it through an `autouse`
fixture of their own — see `tests/test_botting/test_held_keys_ledger.py`.

## Running

`pytest` from the repo root. No flags, no `--ignore`:

```
0 failed, 0 errors, 0 xfailed, 2 deselected
```

**That is the green baseline. Any `failed` or `error` line is yours.**

Don't pin the passing count anywhere — it moved from 270 to 322 in under an hour
once someone else's branch landed. The shape is what holds:

- **2 deselected** — the `system`-marked keyboard-layout tests. Nothing is wrong;
  they are opt-in. Note these are *not* `live` tests: **no test carries the `live`
  marker today**, so `pytest -m live` selects nothing.
- **0 xfailed** — the 11 red tests parked behind issue #89 are resolved: the
  8 unwritten `test_controller.py`/`test_screenshots.py` placeholders were
  deleted (coverage question moved to #34 and #96), the minimap 2px drift was a
  stale fixture (now updated), the OCR text assertion was dropped (`test_from_img`
  already covers the parsing path without asserting Tesseract's output), and the
  `ml_training/` layout assertion had its one stale filename removed.

Never add an `xfail` to get a green run. It is a holding action, not a fix — see
#89 for what that holding action actually cost to resolve.

## Proving a new test earns its place

A test that passes whether or not your change is present proves nothing, and it is
indistinguishable from a real test once it is in the tree. So before a behaviour
change is done, show that its test fails without it.

**With the work uncommitted**, stash only the source paths and leave the test:

```bash
git stash push -- botting/some_module.py          # source only, test untouched
pytest tests/test_botting/test_some_module.py::test_the_new_case
git stash pop
```

**With the work already committed**, use a throwaway worktree at the parent commit
and copy the test into it:

```bash
git worktree add ../verify HEAD~1
cp tests/test_botting/test_some_module.py ../verify/tests/test_botting/
cd ../verify && pytest tests/test_botting/test_some_module.py::test_the_new_case
cd - && git worktree remove ../verify
```

**Read the failure, not just the colour.** A test that errors on an `ImportError`
because the symbol does not exist yet is red for a structural reason; that is
fine when your change adds the symbol, and worthless when your change alters
behaviour of something already there. What you want to see is *your assertion*
failing, with the old value on one side.

State the result where the work is reported: which test, and what it said before.

### Refactors are the opposite case

No new test, and every existing test passes **unmodified**. Editing a test to make
a refactor pass means behaviour moved — which makes it not a refactor. Stop and
say what moved and why, rather than adjusting the assertion to match.

This is the common case in the current backlog: #46 and #76 are both refactors,
and for those the discipline is "don't touch the tests," not "write one first."

### On test-first

Encouraged where it works, which is the same boundary as everything else here:

- **Invariant work** — write the test first if you can, and better still, write it
  from the ticket's acceptance criteria rather than from the implementation you
  have in mind. A test derived from the code it is about to test only records
  your intent; one derived from the spec can contradict you, which is the entire
  point.
- **Expectation work** — test-first is not available. There is no failing test for
  "the character reaches the platform." Do not invent one by pinning a measured
  constant into an assertion and calling it an Invariant; that manufactures a
  test which fails on somebody else's machine for reasons unrelated to the code.

Test-first is a technique, not a rule here. The rule is the one above: the test
fails without the change.

## Changing an existing test

Preserve behaviour. A conversion is syntactic: a test that failed before must fail
after, with the same verdict. Take a per-test baseline first
(`pytest -q --tb=no -rA`), and diff it against the same run afterward.

When a test turns out to be broken, stale, or never collected, leave it that way and
file it separately. Folding a fix into a conversion hides the fix and makes the
conversion impossible to verify.
