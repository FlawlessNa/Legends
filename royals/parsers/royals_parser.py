from botting.communications import BaseParser
from botting.core.action_data import ActionRequest, DiscordRequest


class RoyalsParser(BaseParser):
    """
    Extends the base parser to add the following functions:
    - Kill by Returning to Lounge  # TODO
    - Kill by Logging Out / Closing all clients  # TODO
    - Write functions to General and Whisper chat channels  # TODO
    """

    def pause(self, who: list[str] = None) -> ActionRequest:
        pass

    def resume(self, who: list[str] = None) -> ActionRequest:
        pass

    def write(self, message: str, who: str = None) -> ActionRequest:
        pass
