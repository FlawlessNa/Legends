from botting.communications import BaseParser
from botting.core.action_data import ActionRequest, DiscordRequest
from royals.actions import priorities


class RoyalsParser(BaseParser):

    @staticmethod
    async def _kill() -> None:
        raise KeyboardInterrupt("Kill request from Discord confirmed")

    def kill(self) -> ActionRequest:
        return ActionRequest(
            f"Killing all tasks",
            self._kill,
            ign='All',
            priority=priorities.KILL_SWITCH,
            block_lower_priority=True,
            discord_request=DiscordRequest("Kill request from Discord confirmed")
        )

    def pause(self, who: list[str] = None) -> ActionRequest:
        pass

    def resume(self, who: list[str] = None) -> ActionRequest:
        pass

    def write(self, message: str, who: str = None) -> ActionRequest:
        pass
