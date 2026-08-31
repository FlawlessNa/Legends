# `tests/` — the suite

Every test here is pytest-native. **`docs/agents/testing.md` is the full
convention** — the unittest translation table, the `mocker` rules, and how to
convert a module without changing its behaviour. Read it before writing or
editing a test; what follows is only the shape of the suite.

- Plain module-level `test_*` functions, `@pytest.fixture` for setup, bare
  `assert`. No `TestCase`, and nothing under `tests/` imports `unittest` —
  spies come from `pytest-mock`'s `mocker` fixture.
- **Two opt-in markers**, both deselected by default: `@pytest.mark.live` for
  tests driving a real, focused game client (`pytest -m live`), and
  `@pytest.mark.system` for tests that mutate machine-global state such as the
  machine's keyboard layouts (`pytest -m system`). Anything that needs a game
  window, or leaves a trace outside the test process, belongs behind one.
- **`held_movement_keys`** (root `conftest.py`) pins what
  `KeyboardInputWrapper` construction sees as already held, so the
  Held-Keys Ledger's cross-test state doesn't leak into your assertions.
  Modules that touch the ledger directly reset it with their own `autouse`
  fixture — see `test_botting/test_held_keys_ledger.py`.
- `pytest` from the repo root — no flags, no `--ignore`. Collection completes.
  The suite is **not** green: 8 `pytest.fail()` placeholder stubs and a handful
  of environment-dependent failures remain. `docs/agents/testing.md` lists them
  exactly; anything failing outside that list is yours.
- Converting a test preserves behaviour. Take a baseline
  (`pytest -q --tb=no -rA`) first and diff it after. If you find a test that's
  broken, stale, or never collected, leave it and file it separately.
