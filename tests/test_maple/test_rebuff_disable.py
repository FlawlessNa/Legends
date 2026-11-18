"""
`SoloRebuff` runs one loop per buff. A disable (`_disable_decision_makers`, as
a GM line in `ChatReplies` or a lost map in `CheckStillInMap` sends) must stop
every one of them: until #464 its decision task returned once the loops were
started, so cancelling it stopped nothing and the buffs kept being cast.
"""

import asyncio
import threading
from types import SimpleNamespace

from botting.core import BotData
from maple.decision_makers import SoloRebuff
from tests.test_botting.test_bot_resume import (
    _DaemonThreads,  # pyright: ignore[reportPrivateUsage]
    _loops,  # pyright: ignore[reportPrivateUsage]
    _until,  # pyright: ignore[reportPrivateUsage]
    metadata,  # noqa: F401 - the fixture
)


def _buff(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name, type="Buff", use_by_default=True, duration=60)


def test_a_disable_stops_every_buff_loop(metadata: dict[str, object]) -> None:  # noqa: F811
    data = BotData("Alice")
    data.set_static(
        "character",
        SimpleNamespace(skills={"Bless": _buff("Bless"), "Haste": _buff("Haste")}),
    )
    data.set_static("buffs_reader", SimpleNamespace(read=lambda frame, names: None))
    data.set_static("buff_names", ("Bless", "Haste"))
    data.set_static("current_frame", None)
    rebuff = SoloRebuff(metadata, data, None)  # pyright: ignore[reportArgumentType]
    casts: list[str] = []

    async def recast(buff: SimpleNamespace, condition: threading.Condition) -> None:
        casts.append(buff.name)
        await asyncio.sleep(0.01)

    rebuff._recast = recast  # type: ignore[method-assign]  # pyright: ignore[reportAttributeAccessIssue, reportPrivateUsage]

    async def run() -> None:
        asyncio.get_running_loop().set_default_executor(_DaemonThreads())
        async with asyncio.TaskGroup() as tg:
            await rebuff.start(tg)
            await _until(lambda: len(_loops("SoloRebuff(Alice) - ")) == 2)

            rebuff._disable_decision_makers("SoloRebuff")  # pyright: ignore[reportPrivateUsage]
            await _until(lambda: not _loops("SoloRebuff"))
            cast = len(casts)
            await asyncio.sleep(0.1)
            assert len(casts) == cast, "a buff loop kept casting after the disable"

            for task in _loops("SoloRebuff") + [
                t for t in asyncio.all_tasks() if "abler" in t.get_name()
            ]:
                task.cancel()

    asyncio.run(run())
