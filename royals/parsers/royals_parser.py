from botting.communications import BaseParser
from botting.utilities import take_screenshot
from botting.core.action_data import ActionRequest
from royals.actions import write_in_chat, priorities
from royals.bots.royals_bot import RoyalsBot


class RoyalsParser(BaseParser):
    """
    Extends the base parser to add the following functions:
    - Kill by Returning to Lounge  # TODO
    - Kill by Logging Out / Closing all clients  # TODO
    - Write functions to General and Whisper chat channels  # TODO
    """

    def pause(self, who: list[str] = None) -> str:
        if who is None:
            who = ["All"]
        return f"PAUSE {" ".join(who)}"

    def resume(self, who: list[str] = None) -> str:
        if who is None:
            who = ["All"]
        return f"RESUME {" ".join(who)}"

    def write(self, message: str, who: str = None) -> ActionRequest:
        handle = RoyalsBot.get_handle_from_ign(who)
        return ActionRequest(
            f"Writing Message received from Discord",
            write_in_chat,
            who,
            priorities.USER_REQUESTS,
            block_lower_priority=True,
            args=(handle, message),
            cancel_tasks=[
                f"Rotation({who})",
                f"MobsHitting({who})",
                f"TelecastMobsHitting({who})",
            ],

            callbacks=[
                lambda: self._confirmation_with_image(handle)
            ]
        )

    def _confirmation_with_image(self, handle: int) -> None:
        img = take_screenshot(handle)
        self.pipe.send(img)
