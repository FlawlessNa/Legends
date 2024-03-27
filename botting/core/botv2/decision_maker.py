import logging
import multiprocessing.managers
import time
from abc import ABC, abstractmethod
from typing import Literal

from .bot_data import BotData
from .action_data import ActionRequest

logger = logging.getLogger(__name__)


class SkipCall(Exception):
    pass


class DecisionMaker(ABC):
    """
    Abstract base class to represent a decision maker of any kind.
    Each Bot consists of one or more DecisionMaker, which are cycled and called
    one at a time.
    When called, a DecisionMaker may return an ActionRequest container,
    which will be sent to the Main Process to be executed there.
    """

    _type: Literal["Rotation", "AntiDetection", "Maintenance"]
    skip = SkipCall

    def __init__(
        self, metadata: multiprocessing.managers.DictProxy, data: BotData
    ) -> None:
        self.metadata = metadata
        self.data = data
        self.metadata["Blockers"][self.data.ign][self._type][id(self)] = 0
        self._blocked_at = None
        self._previously_blocked = False

    @property
    def blocked(self) -> bool:
        """
        Returns True if the DecisionMaker is blocked by any DecisionMaker, including
        itself. Returns False otherwise.
        """
        val = self.metadata["Blockers"][self.data.ign][self._type][id(self)]
        assert val >= 0, f"Blocking counter for {self} is negative."
        return val > 0

    @blocked.setter
    def blocked(self, value: bool):
        """
        Used by a DecisionMaker to block/unblock itself.
        :param value: If True, increments blocking counter for this DecisionMaker. Else,
        decrements it.
        :return:
        """
        if value:
            if not self.blocked:
                logger.debug(f"{self} has been blocked.")

            self.metadata["Blockers"][self.data.ign][self._type][id(self)] += 1

        else:
            was_blocked = self.blocked
            self.metadata["Blockers"][self.data.ign][self._type][id(self)] -= 1
            if was_blocked and not self.blocked:
                logger.debug(f"{self} has been unblocked.")

    @property
    def blocked_at(self) -> float | None:
        """
        Returns the approx. time at which DecisionMaker was blocked, if it is blocked.
        None otherwise.
        """
        if self.blocked:
            if not self._previously_blocked:
                self._blocked_at = time.perf_counter()
            self._previously_blocked = True
        else:
            self._blocked_at = None
            self._previously_blocked = False
        return self._blocked_at

    def block(
        self,
        type_to_block: Literal["Rotation", "AntiDetection", "Maintenance", "All"],
        bot: str = None,
    ) -> None:
        """
        Blocks all DecisionMaker of a given type for the specified bot.
        :param type_to_block: The type of DecisionMakers to block.
        :param bot: The bot to block. If None, defaults to the bot containing self.
        :return:
        """
        if type_to_block == "All":
            for type_ in self.metadata["Blockers"][bot]:
                self.block(type_, bot)
        else:
            self._update_blockers(type_to_block, bot, 1)

    def unblock(
        self,
        type_to_unblock: Literal["Rotation", "AntiDetection", "Maintenance", "All"],
        bot: str = None,
    ) -> None:
        """
        Unblocks all DecisionMaker of a given type for the specified bot.
        :param type_to_unblock: The type of DecisionMakers to unblock.
        :param bot: The bot to unblock. If None, defaults to the bot containing self.
        :return:
        """
        if type_to_unblock == "All":
            for type_ in self.metadata["Blockers"][bot]:
                self.unblock(type_, bot)
        else:
            self._update_blockers(type_to_unblock, bot, -1)

    def _update_blockers(
        self,
        type_to_block: Literal["Rotation", "AntiDetection", "Maintenance", "All"],
        bot: str,
        increment: int,
    ):
        assert increment in (-1, 1), f"Increment must be -1 or 1, not {increment}."
        if bot is None:
            bot = self.data.ign

        for decision_maker_id in self.metadata["Blockers"][bot][type_to_block]:
            if decision_maker_id == id(self):
                continue
            self.metadata["Blockers"][bot][type_to_block][
                decision_maker_id
            ] += increment

    # def freeze(self, bots: list[str] | str | None = None) -> None:
    #     """
    #     Used by a higher level entity, such as the Bot itself or an Engine, to block
    #     all DecisionMakers for one or multiple bots.
    #     :return:
    #     """
    #     if isinstance(bots, str):
    #         for type_to_block in self.metadata["Blockers"][bots]:
    #             self.block(type_to_block, bots)
    #     elif isinstance(bots, list):
    #         for bot in bots:
    #             self.freeze(bot)
    #     elif bots is None:
    #         for bot in self.metadata["Blockers"]:
    #             self.freeze(bot)

    @abstractmethod
    def __repr__(self) -> str:
        pass

    @abstractmethod
    def _call(self, *args, **kwargs) -> ActionRequest | None:
        pass

    def __call__(self, *args, **kwargs) -> ActionRequest | None:
        blocked_since = self.blocked_at
        if blocked_since and time.perf_counter() - blocked_since > 300:
            raise RuntimeError(
                f"{self} has been blocked for more than 5 minutes. Exiting."
            )
        if self.blocked:
            return

        return self._call(*args, **kwargs)
