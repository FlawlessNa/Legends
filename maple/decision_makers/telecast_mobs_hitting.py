import functools
import logging

from botting import PARENT_LOG
from botting.core import ActionRequest
from maple.actions.movements_v2 import telecast_compiler
from maple.model.characters import MapleSkill
from maple.model.mechanics import MovementTypes
from maple.telemetry_events import COMBAT_TELECAST, TelecastPayload

from .mobs_hitting import MobsHitting
from .providers import HANDLE, MOVEMENTS, SKILLS, PathingProvider, pathing

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

_TELEPORT_MOVEMENTS = frozenset(
    {
        MovementTypes.TELEPORT_LEFT,
        MovementTypes.TELEPORT_RIGHT,
        MovementTypes.TELEPORT_UP,
        MovementTypes.TELEPORT_DOWN,
    }
)


class TelecastMobsHitting(MobsHitting):
    """
    Casts the training skill *through* the movement instead of standing still for it,
    by fusing the ultimate's key into the teleport keydowns of the Movement Plan that
    is about to be dispatched.

    The plan and every compile input are frozen by `PathingProvider.compiler`,
    exactly the way rotation freezes them, so a telecast and the movement it
    replaces compile from identical inputs. The plan is the rotation's:
    `PathingProvider` plans it, and this DecisionMaker reads it (`MOVEMENTS`).
    """

    reads = (*MobsHitting.reads, MOVEMENTS)

    def setup(self) -> None:
        super().setup()
        #: The teleport its casts are fused into.
        self._teleport_skill: MapleSkill = self.read(SKILLS)["Teleport"]
        #: The Bot's pathing, which compiles the plan the cast is fused into.
        self._pathing: PathingProvider = pathing(self.data)

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
        return any(
            move.movement_type in _TELEPORT_MOVEMENTS for move in self.read(MOVEMENTS)
        )

    def _hit_mobs(self, direction: str | None) -> ActionRequest:
        # A telecast faces where the movement goes: the facing is not used, and
        # the plain cast it falls back to has no facing prelude either.
        del direction
        if not self._teleport_in_movement_plan():
            return super()._hit_mobs(direction=None)

        fused: TelecastPayload = {
            "teleport_skill": self._teleport_skill.name,
            "ultimate_skill": self.training_skill.name,
        }
        self.emit(COMBAT_TELECAST, fused)
        compiler = functools.partial(
            telecast_compiler,
            # The Path is the rotation's: no frame of its own to lead from.
            movement_compiler=self._pathing.compiler(self.correlation_id, lead=False),
            handle=self.read(HANDLE),
            ign=self.data.ign,
            teleport_skill=self._teleport_skill,
            ultimate_skill=self.training_skill,
            # Baked in rather than passed to the procedure: the compile runs in
            # Main Process, and only this partial - built inside `_decide()` -
            # knows which decision it belongs to.
            correlation_id=self.correlation_id,
        )
        return self._cast_request(compiler)
