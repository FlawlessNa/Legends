import asyncio
import multiprocessing

from botting import EngineData, Executor, SessionManager
from botting.core import DecisionEngine, DecisionGenerator
from botting.utilities import client_handler
from royals.engines.generators import InventoryManager
from royals import RoyalsData, royals_ign_finder
from royals.maps import RoyalsMap, PathOfTime1


IGN = "WrongDoor"
GENERATOR = InventoryManager
CURRENT_MAP = PathOfTime1

DATA_INSTANCE = RoyalsData(
    handle=client_handler.get_client_handle(IGN, royals_ign_finder),
    ign=IGN,
    current_map=PathOfTime1(),
)
ENGINE_KWARGS = {}


class MockEngine(DecisionEngine):
    ign_finder = royals_ign_finder

    def __init__(
        self,
        log_queue: multiprocessing.Queue,
        bot: Executor,
    ) -> None:
        super().__init__(log_queue, bot)
        self._game_data = DATA_INSTANCE

    @property
    def anti_detection_checks(self) -> list[DecisionGenerator]:
        if GENERATOR.generator_type == "AntiDetection":
            return [GENERATOR(self.game_data)]
        return []

    @property
    def next_map_rotation(self) -> DecisionGenerator:
        if GENERATOR.generator_type == "Rotation":
            return GENERATOR(self.game_data)

    @property
    def items_to_monitor(self) -> list[DecisionGenerator]:
        if GENERATOR.generator_type == "Maintenance":
            return [GENERATOR(self.game_data)]
        return []

    @property
    def game_data(self) -> EngineData:
        return self._game_data


async def main(*bots: Executor) -> None:
    with SessionManager(*bots) as session:
        await session.launch()


if __name__ == "__main__":
    executor = Executor(engine=MockEngine, ign=IGN, **ENGINE_KWARGS)
    asyncio.run(main(executor))
