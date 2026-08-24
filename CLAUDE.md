## Agent skills

### Issue tracker

Issues live in GitHub Issues on `FlawlessNa/Legends`, via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical label vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`) — identity mapping. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` plus `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Tests

pytest-native, always: plain module-level `test_*` functions, `@pytest.fixture` in place of `setUp`/`tearDown`, and bare `assert`. This holds for new test modules and for any unittest-style test you touch. See `docs/agents/testing.md` for the translation table, the `live` marker, the shared fixtures, and how to convert a module without changing its behaviour.
