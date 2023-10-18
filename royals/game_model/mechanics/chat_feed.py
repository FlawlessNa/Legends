class ChatFeed(list):
    def __init__(self, nbr_lines_displayed: int):
        super().__init__(self)
        self.nbr_lines_displayed: int = nbr_lines_displayed

    def visible_lines(self) -> list[str]:
        return self[-self.nbr_lines_displayed :]
