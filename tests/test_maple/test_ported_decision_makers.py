"""
A ported DecisionMaker has no mixin in its class hierarchy, and declares the
Data Keys it reads (ADR 0004; `docs/agents/decision-makers.md`).
"""

import pytest

from botting.core import DecisionMaker
from maple.decision_makers import (
    ChatReplies,
    CheckMobsStillSpawn,
    CheckStillInMap,
    MobsHitting,
    MountFood,
    PetFood,
    SoloRebuff,
    SpeedPill,
    TelecastMobsHitting,
    TrialRunner,
)

PORTED = (
    CheckStillInMap,
    MobsHitting,
    TelecastMobsHitting,
    SoloRebuff,
    PetFood,
    SpeedPill,
    MountFood,
    ChatReplies,
    CheckMobsStillSpawn,
    TrialRunner,
)


@pytest.mark.parametrize("cls", PORTED, ids=lambda cls: cls.__name__)
def test_a_ported_decision_maker_has_no_mixin_and_declares_its_reads(
    cls: type[DecisionMaker],
) -> None:
    mixins = [
        base.__name__
        for base in cls.__mro__
        if base.__module__.startswith("maple.decision_makers.mixins")
    ]

    assert mixins == []
    assert cls.reads
