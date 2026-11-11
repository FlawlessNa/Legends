from botting.communications import BaseParser
from botting.core.action_data import ActionRequest
from botting.screen import frame_source
from maple.actions import priorities, write_in_chat
from maple.screen.client import find_client


class MapleParser(BaseParser):
    """
    Extends the base parser to add the following functions:
    - Kill by Returning to Lounge  # TODO
    - Kill by Logging Out / Closing all clients  # TODO
    - Write functions to General and Whisper chat channels  # TODO
    """

    def pause(self, who: list[str] | None = None) -> str:
        if who is None:
            who = ["All"]
        return f"PAUSE {' '.join(who)}"

    def resume(self, who: list[str] | None = None) -> str:
        if who is None:
            who = ["All"]
        return f"RESUME {' '.join(who)}"

    def write(
        self,
        message: str,
        who: str | None = None,
        *,
        to: str | None = None,
        channel: str | None = None,
    ) -> ActionRequest:
        assert who is not None, "BaseParser names the IGN before it calls write"
        handle = find_client()
        return ActionRequest(
            "Writing Message received from Discord",
            write_in_chat,
            who,
            priorities.USER_REQUESTS,
            block_lower_priority=True,
            args=(handle, message),
            kwargs=self._where(to, channel),
            cancel_tasks=[
                f"Rotation({who})",
                f"MobsHitting({who})",
                f"TelecastMobsHitting({who})",
            ],
            callbacks=[lambda: self._confirmation_with_image(handle)],
        )

    @staticmethod
    def _where(to: str | None, channel: str | None) -> dict[str, str]:
        """The channel and whisper target `write_in_chat` is given."""
        if to is not None:
            return {"channel": "whisper", "whisper_to": to}
        return {"channel": channel or "general"}

    def _confirmation_with_image(self, handle: int) -> None:
        frame = frame_source().grab(handle)
        if not frame.ok:
            self.pipe.send(f"Could not capture the client: {frame.reason}")
            return
        self.pipe.send(frame.pixels)
