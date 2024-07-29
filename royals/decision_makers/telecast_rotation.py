import math
from botting.core.botv2.decision_maker import DecisionMaker

DISTANCE_THRESHOLD = 10


class TelecastRotation(DecisionMaker):

    def __repr__(self) -> str:
        pass

    async def _decide(self) -> None:
        self.next_target = self.data.next_target or self._set_next_target()

    def _set_next_target(self) -> tuple[int, int]:
        if math.dist(self.data.current_minimap_position, self.next_target) > DISTANCE_THRESHOLD:
            return self.next_target
        else:
            pass
