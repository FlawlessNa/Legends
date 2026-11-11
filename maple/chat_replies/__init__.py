"""
Answering players who talk to the character (#455): the pieces, as plain classes
and functions, with no DecisionMaker, mixin, process or `BotData` in them.

- `conversation`: the session's chat as one conversation, and what is left to
  answer;
- `addressing`: whether a line must be answered, may be, or is ignored;
- `instructions`: what the model answers with.

`ChatReplies` (`maple/decision_makers/`) runs them.
"""
