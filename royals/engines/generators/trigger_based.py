# import logging
# import time
#
# from abc import ABC, abstractmethod
# from functools import partial
#
# from botting import PARENT_LOG
# from botting.core import DecisionGenerator, QueueAction, GameData
#
#
# logger = logging.getLogger(PARENT_LOG + "." + __name__)
#
#
# class TriggerBasedGenerator(DecisionGenerator, ABC):
#     """
#     Base class for generators that perform an action at a given interval.
#     """
#
#     def __init__(
#         self,
#         data: GameData,
#     ) -> None:
#         super().__init__(data)
#
#     def _get_status(self) -> str:
#         if time.perf_counter() < self._next_call:
#             return "Idle"
#         else:
#             return getattr(self.data, f"{repr(self)}_status")
#
#     def _set_status(self, status: str):
#         setattr(self.data, f"{repr(self)}_status", status)
#
#     def _failsafe(self):
#         if self._fail_count > 10:
#             logger.critical(f"{repr(self)} has failed too many times. Stopping.")
#             return QueueAction(
#                 identifier=f"{repr(self)} Failsafe",
#                 priority=1,
#                 action=partial(lambda: RuntimeError, f"{repr(self)} Failsafe"),
#                 user_message=[f"{repr(self)} has failed too many times. Stopping."]
#             )
#
#     def _next(self):
#         status = self._get_status()
#         if status == "Idle":
#             return
#         elif status == "Setup":
#             # Once the generator is ready to be executed, block others of the same type
#             self.data.block(self.generator_type, excepted=repr(self))
#             return self._setup()  # _setup responsible for setting status to "Ready"
#         elif status == "Ready":
#             self._update_attributes()
#             self._set_status("Idle")
#             return self._trigger()  # _trigger responsible for setting status to "Done"
#         elif status == "Done":
#             if not self._confirm_cleaned_up():
#                 self._set_status("Idle")
#                 return QueueAction(
#                     identifier=f"{self.__class__.__name__} - Cleanup",
#                     priority=1,
#                     action=self._cleanup_action(),
#                     is_cancellable=False,
#                     update_generators={f"{repr(self)}_status": "Done"},
#                 )
#             else:
#                 self.data.unblock(self.generator_type)
#                 self._set_status("Setup")
#                 self._next_call = time.perf_counter() + self.interval
#                 self._fail_count = 0
#                 return
#
#     @abstractmethod
#     def _cleanup_action(self) -> partial:
#         pass
#
#     @abstractmethod
#     def _confirm_cleaned_up(self) -> bool:
#         pass
#
#     @abstractmethod
#     def _update_attributes(self) -> None:
#         pass
#
#     @abstractmethod
#     def _setup(self) -> QueueAction:
#         pass
#
#     @abstractmethod
#     def _trigger(self) -> QueueAction:
#         pass
