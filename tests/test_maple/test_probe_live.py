"""
The probe against a real, open client. Deselected by default: `pytest -m live`, with
`PROBE_IGN` naming the character to drive.

This checks only the Held-Keys Ledger. Whether the character actually stopped is for
the human watching it.
"""

import json
import os

import pytest

from botting.controller.inputs import HeldKeysLedger
from maple import probe


@pytest.mark.live
def test_hold_right_for_500ms_leaves_nothing_held(
    capsys: pytest.CaptureFixture[str],
) -> None:
    ign = os.environ.get("PROBE_IGN")
    if not ign:
        pytest.skip("Set PROBE_IGN to the IGN of an open client.")

    assert probe.main(["hold", "right", "--ms", "500", "--ign", ign]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["held_after"] == []
    handle = probe.resolve_handle(ign)
    assert HeldKeysLedger.keys_held(handle) == frozenset()
