"""
The probe against a real, open client. Deselected by default: `pytest -m live`.

This checks only the Held-Keys Ledger. Whether the character actually stopped is for
the human watching it.
"""

import json

import pytest

from botting.controller.inputs import HeldKeysLedger
from maple import probe


@pytest.mark.live
def test_hold_right_for_500ms_leaves_nothing_held(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert probe.main(["hold", "right", "--ms", "500"]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["held_after"] == []
    assert HeldKeysLedger.keys_held(probe.resolve_handle()) == frozenset()
