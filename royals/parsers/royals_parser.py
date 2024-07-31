from botting.communications import BaseParser
from botting.core.action_data import ActionRequest


class RoyalsParser(BaseParser):
    def kill(self) -> ActionRequest:
        pass

    def pause(self, who: list[str] = None) -> ActionRequest:
        pass

    def resume(self, who: list[str] = None) -> ActionRequest:
        pass

    def write(self, message: str, who: str = None) -> ActionRequest:
        pass
