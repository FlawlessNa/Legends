"""
Corpus fixtures shared by `test_invariants.py` and `test_goldens.py`.

Parametrizing on the `CorpusMap` object itself, rather than a bare name, keeps every
fixture built from the exact key `corpus.py`'s own `@cache`d loaders use - so
`corpus_handler`/`corpus_plans` below hit that cache instead of rebuilding a map's
graph or recompiling its sample a second time.

A real map reads the game data store, so its cases carry the `client_files` marker:
the default suite runs the Fixture maps only.
"""

from __future__ import annotations

import pytest

from maple.model.mechanics import movement_mechanics_v2
from maple.model.mechanics.movement_mechanics_v2 import MovementHandler
from tests.test_maple.movement_lab import corpus

CORPUS_IDS = [entry.name for entry in corpus.CORPUS]

#: Every Corpus map as a pytest parameter, a real one marked `client_files`.
CORPUS_PARAMS = [
    pytest.param(
        entry,
        id=entry.name,
        marks=[pytest.mark.client_files] if entry.source == "client" else [],
    )
    for entry in corpus.CORPUS
]

# The jump builders resolve their key bind through `key_binds`, which reads a
# gitignored personal config (`configs/keybindings.ini`) - compiling any Movement Plan
# with a `JUMP*` component would otherwise fail on a clean checkout.
# `corpus.LAB_TELEPORT` covers the same gap for the Teleport skill's own key bind.
JUMP_KEY = "space"


@pytest.fixture(autouse=True)
def jump_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        movement_mechanics_v2, "key_binds", lambda ign: {"jump": JUMP_KEY}
    )


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "corpus_map" in metafunc.fixturenames:
        metafunc.parametrize("corpus_map", CORPUS_PARAMS)


@pytest.fixture
def corpus_handler(corpus_map: corpus.CorpusMap) -> MovementHandler:
    return corpus.handler(corpus_map)


@pytest.fixture
def corpus_plans(corpus_map: corpus.CorpusMap) -> tuple[corpus.PlanRecord, ...]:
    return corpus.plans(corpus_map)
