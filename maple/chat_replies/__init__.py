"""
Answering players who talk to the character (#455): the pieces, as plain classes
and functions, with no DecisionMaker, mixin, process or `BotData` in them.

- `line`: what the reply side reads from a chat line, and whether two names
  read are one;
- `addressing`: whether a line must be answered, may be, or is ignored;
- `conversation`: the session's chat as one conversation, and what is left to
  answer;
- `instructions`: what the model answers with;
- `relay`: from the conversation to a reply, one request to the model;
- `mirror`: each exchange, as posted on Discord.

`ChatReplies` (`maple/decision_makers/`) runs them.
"""
