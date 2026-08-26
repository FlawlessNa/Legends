import functools
import logging

from botting import PARENT_LOG
from botting.core import ActionRequest
from maple.actions.movements_v2 import telecast_compiler
from maple.model.mechanics import MovementTypes

from .mixins import MovementsMixin
from .mobs_hitting import MobsHitting

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")
LOG_LEVEL = logging.INFO

_TELEPORT_MOVEMENTS = frozenset(
    {
        MovementTypes.TELEPORT_LEFT,
        MovementTypes.TELEPORT_RIGHT,
        MovementTypes.TELEPORT_UP,
        MovementTypes.TELEPORT_DOWN,
    }
)


class TelecastMobsHitting(MovementsMixin, MobsHitting):
    """
    Casts the training skill *through* the movement instead of standing still for it,
    by fusing the ultimate's key into the teleport keydowns of the Movement Plan that
    is about to be dispatched.

    Inherits `MovementsMixin` purely for `_movement_compiler`: the plan and every
    compile input are frozen exactly the way rotation freezes them, so a telecast and
    the movement it replaces compile from identical inputs. The pathing attributes
    themselves are created by `Rotation` on the shared `BotData`; this DecisionMaker
    only reads them.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._teleport_skill = self.data.character.skills["Teleport"]

    def _teleport_in_movement_plan(self) -> bool:
        """
        Whether the Movement Plan about to be dispatched holds any teleport.

        Replaces `teleport_key in self.data.action.keys`, a question that can
        only be asked of a compiled Input Sequence - and nothing is compiled in this
        process any more (ADR 0002). The two are equivalent: the teleport key reaches
        an Input Sequence only through `movements_v2.teleport`, which
        `compile_movements` calls only for a `TELEPORT_*` component. The plan check is
        true in one case the compiled check was not - a plan whose teleports all fall
        past `total_duration` and are truncated away - which is exactly the case
        `telecast_compiler` falls back to a plain cast for.
        """
        if not self.data.has_pathing_attributes:
            return False
        movements = self.data.movements
        return any(
            move.movement_type in _TELEPORT_MOVEMENTS for move in movements or ()
        )

    def _hit_mobs(self, *args, **kwargs) -> ActionRequest:
        if not self._teleport_in_movement_plan():
            return super()._hit_mobs(direction=None)

        logger.log(LOG_LEVEL, f"{self} is about to Telecast.")
        compiler = functools.partial(
            telecast_compiler,
            movement_compiler=self._movement_compiler(),
            handle=self.data.handle,
            ign=self.data.ign,
            teleport_skill=self._teleport_skill,
            ultimate_skill=self.training_skill,
        )
        return self._cast_request(compiler)
