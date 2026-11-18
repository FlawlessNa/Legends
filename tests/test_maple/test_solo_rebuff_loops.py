"""
`SoloRebuff` runs one decision loop per buff by declaring them through `loops()`,
the one method a DecisionMaker with several loops overrides (ADR 0004). The
Supervisor runs, pauses and restarts them; `SoloRebuff` holds no TaskGroup.
"""

import asyncio
import threading
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from pytest_mock import MockerFixture

from botting.core import DecisionMaker, ProxyFactory
from maple.decision_makers.rebuffs import SoloRebuff
from maple.model.characters.maple_skills import MapleBuff, MapleSkill
from tests.test_maple.serving import assemble, serve

HASTE = MapleBuff("Haste", duration=200, _use_by_default=True)
BLESS = MapleBuff("Bless", duration=300, _use_by_default=True)


@dataclass
class _Character:
    skills: dict[str, MapleSkill] = field(
        default_factory=lambda: {"Haste": HASTE, "Bless": BLESS}
    )


@pytest.fixture
def rebuff(monkeypatch: pytest.MonkeyPatch, mocker: MockerFixture) -> SoloRebuff:
    # The per-buff Conditions are Manager proxies in a Session; a local one
    # behaves the same for anything that does not cross a process.
    mocker.patch.object(
        ProxyFactory, "instance", side_effect=lambda *_a, **_k: threading.Condition()
    )
    # The buffs reader `BuffsProvider` reads once at setup; nothing here reads
    # the buffs.
    served = serve(
        monkeypatch,
        "Buffer",
        buffs=SimpleNamespace(read=lambda frame, names: None),
        character=_Character(),
        buff_names=("Haste", "Bless"),
    )
    assemble(served, SoloRebuff)
    rebuff = SoloRebuff({}, served.data, mocker.Mock())  # pyright: ignore[reportArgumentType] - no Manager needed
    rebuff.setup()
    return rebuff


def test_solo_rebuff_declares_one_loop_per_buff(rebuff: SoloRebuff) -> None:
    assert [loop.name for loop in rebuff.loops()] == [
        "SoloRebuff(Buffer) - Haste",
        "SoloRebuff(Buffer) - Bless",
    ]


def test_each_loop_recasts_its_own_buff(
    rebuff: SoloRebuff, mocker: MockerFixture
) -> None:
    recast = mocker.patch.object(rebuff, "_recast", new=mocker.AsyncMock())
    loops = rebuff.loops()

    for loop in loops:
        asyncio.run(loop.decide())

    assert [call.args[0] for call in recast.call_args_list] == [HASTE, BLESS]


def test_a_restart_reuses_each_buffs_condition(rebuff: SoloRebuff) -> None:
    """`loops()` is asked again at every restart; it builds no new proxy."""
    first = [loop.decide for loop in rebuff.loops()]
    second = [loop.decide for loop in rebuff.loops()]
    assert [d.args[1] for d in first] == [d.args[1] for d in second]  # pyright: ignore[reportFunctionMemberAccess] - partials


def test_solo_rebuff_leaves_starting_to_the_supervisor() -> None:
    assert "loops" in vars(SoloRebuff)
    assert not hasattr(DecisionMaker, "start")
    assert not hasattr(DecisionMaker, "task")
