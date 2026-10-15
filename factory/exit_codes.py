"""
The factory's exit-code contract.

Every `factory` command returns one of these, and nothing else. The contract is
what turns "stop and ask rather than finishing" from a judgment an agent makes
into a value it reads: `NEEDS_HUMAN` is a return code, not a feeling.

`MISUSE` is deliberately 2 because that is what `argparse` already exits with on
a bad invocation, so the parser's own failures land in the right bucket without
being wrapped.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """What a factory command's exit status means to its caller."""

    #: The gate passed. Continue to the next stage.
    OK = 0
    #: The gate failed. Fix it and re-run; never proceed past this.
    GATE_FAILED = 1
    #: Wrong arguments, or the wrong stage for this command. Re-read `factory next`.
    MISUSE = 2
    #: This needs a person. Stop, comment on the ticket, hand back.
    NEEDS_HUMAN = 3
