"""Kinds of message an Engine can send to Discord."""


class QuietMessage(str):
    """
    A message for Discord that does not ring the maintainer.

    Every other string sent to Discord starts with the maintainer's mention.
    This one is posted as it is, so a stream of them (the chat mirror) can be
    read without a notification each.
    """

    __slots__ = ()
