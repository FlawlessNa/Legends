from functools import cached_property
from typing import TYPE_CHECKING, ClassVar

from botting.core import ActionRequest, BotData
from maple.decision_makers.reactions import Reactions


class ReactionsMixin:
    """
    Legacy: reactions for an unported DecisionMaker, through the `Reactions` it
    holds, which reads its keys from `BotData` by name. A ported DecisionMaker
    holds a `Reactions` itself. Goes with the last mixin.
    """

    data: BotData
    if TYPE_CHECKING:
        # The DecisionMaker's: declared, not defined, so it never shadows it.
        def send(
            self, request: ActionRequest, correlation_id: str | None = None
        ) -> None: ...

    _light_reactions: ClassVar[list[str]] = Reactions.LIGHT
    _advanced_reactions: ClassVar[list[str]] = Reactions.ADVANCED

    @cached_property
    def _reactions(self) -> Reactions:
        return Reactions(self, self.data)

    def _react(self, reaction_type: str, disc_msg: str | None = None) -> None:
        """
        Reacts to a certain event by sending a message to the chat, within
        `Reactions.react`'s cooldown, which every holder in the process shares.
        """
        self._reactions.react(reaction_type, disc_msg)
