import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.utilities import (
    CLIENT_HORIZONTAL_MARGIN_PX,
    CLIENT_VERTICAL_MARGIN_PX,
    Box,
)
from maple import probe

HANDLE = 4242
IMAGE = np.zeros((306, 412, 3), dtype=np.uint8)


@pytest.fixture
def shot(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> MagicMock:
    """Mocks the window, the capture and the output folder; returns the capture mock."""
    monkeypatch.setattr(probe, "PROBE_DIR", tmp_path / "probe")
    mocker.patch.object(probe, "get_open_clients", return_value=[HANDLE])
    mocker.patch.object(probe, "_client_size", return_value=(1024, 768))
    return mocker.patch.object(probe, "take_screenshot", return_value=IMAGE)


def _out(capsys: pytest.CaptureFixture[str]) -> dict:
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


# --- sources ----------------------------------------------------------------


def test_no_flag_captures_the_whole_window(
    shot: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert probe.main(["screenshot"]) == 0

    shot.assert_called_once_with(HANDLE)
    out = _out(capsys)
    assert (out["ok"], out["w"], out["h"]) == (True, 412, 306)
    assert out["path"].endswith("_window.png")


def test_a_static_region_passes_its_box(
    shot: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert probe.main(["screenshot", "--region", "hp_bar"]) == 0

    shot.assert_called_once_with(HANDLE, probe.STATIC_REGIONS["hp_bar"])
    assert _out(capsys)["path"].endswith("_hp_bar.png")


def test_a_dynamic_region_passes_the_box_it_found(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    found = Box(left=10, right=50, top=20, bottom=60)
    mocker.patch.dict(probe.DYNAMIC_REGIONS, {"minimap": lambda h, i: found})

    assert probe.main(["screenshot", "--region", "minimap"]) == 0

    shot.assert_called_once_with(HANDLE, found)
    assert _out(capsys)["path"].endswith("_minimap.png")


def test_box_is_png_coordinates_shifted_by_the_client_margins(
    shot: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    assert probe.main(["screenshot", "--box", "0,0,100,50"]) == 0

    (handle, box), _ = shot.call_args
    assert handle == HANDLE
    assert (box.left, box.top, box.right, box.bottom) == (
        CLIENT_HORIZONTAL_MARGIN_PX,
        CLIENT_VERTICAL_MARGIN_PX,
        100 + CLIENT_HORIZONTAL_MARGIN_PX,
        50 + CLIENT_VERTICAL_MARGIN_PX,
    )
    assert _out(capsys)["path"].endswith("_box.png")


def test_window_box_adds_the_margins() -> None:
    box = probe.window_box(5, 6, 15, 26)

    assert (box.left, box.top, box.right, box.bottom) == (
        5 + CLIENT_HORIZONTAL_MARGIN_PX,
        6 + CLIENT_VERTICAL_MARGIN_PX,
        15 + CLIENT_HORIZONTAL_MARGIN_PX,
        26 + CLIENT_VERTICAL_MARGIN_PX,
    )


def test_region_and_box_together_are_a_usage_error(
    shot: MagicMock, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as raised:
        probe.main(["screenshot", "--region", "ign", "--box", "0,0,10,10"])

    assert raised.value.code == 2
    shot.assert_not_called()


@pytest.mark.parametrize(
    "box", ["1,2,3", "a,b,c,d", "10,0,5,5", "0,10,5,5", "-1,0,5,5"]
)
def test_a_malformed_box_is_a_usage_error(shot: MagicMock, box: str) -> None:
    with pytest.raises(SystemExit) as raised:
        probe.main(["screenshot", "--box", box])

    assert raised.value.code == 2
    shot.assert_not_called()


def test_a_box_outside_the_window_writes_nothing(
    shot: MagicMock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert probe.main(["screenshot", "--box", "0,0,2000,50"]) == 1

    assert "outside" in capsys.readouterr().err
    shot.assert_not_called()
    assert not (tmp_path / "probe").exists()


# --- a missing region -------------------------------------------------------


def test_a_dynamic_region_that_is_not_showing_exits_3_and_writes_nothing(
    shot: MagicMock,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch.dict(probe.DYNAMIC_REGIONS, {"inventory": lambda h, i: None})

    code = probe.main(["screenshot", "--region", "inventory"])

    captured = capsys.readouterr()
    assert code == 3
    assert "inventory" in captured.err
    assert captured.out == ""
    shot.assert_not_called()
    assert not (tmp_path / "probe").exists()


# --- the prune --------------------------------------------------------------


def test_prune_keeps_the_50_most_recent(tmp_path: Path) -> None:
    for i in range(60):
        (tmp_path / f"2026-01-01_00-00-00-{i:03d}_window.png").write_bytes(b"")
    (tmp_path / "notes.txt").write_text("not a png")

    probe.prune(tmp_path)

    names = sorted(p.name for p in tmp_path.glob("*.png"))
    assert len(names) == 50
    assert names[0].endswith("-010_window.png")
    assert (tmp_path / "notes.txt").exists()


def test_each_write_prunes_the_folder(shot: MagicMock, tmp_path: Path) -> None:
    folder = tmp_path / "probe"
    folder.mkdir()
    for i in range(50):
        (folder / f"2000-01-01_00-00-00-{i:03d}_window.png").write_bytes(b"")

    assert probe.main(["screenshot"]) == 0

    assert len(list(folder.glob("*.png"))) == 50


def test_file_names_carry_milliseconds() -> None:
    stamp = probe._timestamp(datetime(2026, 11, 3, 4, 5, 6, 789000, tzinfo=UTC))

    assert stamp == "2026-11-03_04-05-06-789"


# --- window choice ----------------------------------------------------------


def test_ign_resolves_the_window_through_get_client_handle(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    get = mocker.patch.object(probe, "get_client_handle", return_value=77)

    assert probe.main(["screenshot", "--ign", "Alice"]) == 0

    get.assert_called_once_with("Alice", probe.maple_ign_finder)
    shot.assert_called_once_with(77)


def test_no_client_open_exits_4(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "get_open_clients", return_value=[])

    assert probe.main(["screenshot"]) == 4

    assert "No game client" in capsys.readouterr().err
    shot.assert_not_called()


def test_several_clients_exit_5_and_are_listed(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "get_open_clients", return_value=[1, 2])
    mocker.patch.object(
        probe, "maple_ign_finder", side_effect=lambda h: {1: "Alice", 2: "Bob"}[h]
    )

    assert probe.main(["screenshot"]) == 5

    err = capsys.readouterr().err
    assert "1 (Alice)" in err
    assert "2 (Bob)" in err
    shot.assert_not_called()


# --- regions and keys -------------------------------------------------------


def test_regions_lists_every_name_and_whether_dynamic_ones_show(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.dict(
        probe.DYNAMIC_REGIONS,
        {
            "minimap": lambda h, i: Box(left=0, right=1, top=0, bottom=1),
            "inventory": lambda h, i: None,
            "chat": lambda h, i: None,
        },
        clear=True,
    )

    assert probe.main(["regions"]) == 0

    out = _out(capsys)
    assert out["static"] == ["ign", "level", "job", "hp_bar", "mp_bar", "exp_bar"]
    assert out["dynamic"] == {"minimap": True, "inventory": False, "chat": False}


def test_keys_lists_the_binding_names_of_the_only_clients_ign(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "maple_ign_finder", return_value="Alice")
    binds = mocker.patch.object(
        probe, "key_binds", return_value={"inventory menu": "i", "attack": "a"}
    )

    assert probe.main(["keys"]) == 0

    binds.assert_called_once_with("Alice")
    assert _out(capsys) == {
        "ok": True,
        "ign": "Alice",
        "keys": ["attack", "inventory menu"],
    }


def test_keys_with_ign_does_not_read_the_ign_off_the_screen(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "get_client_handle", return_value=77)
    finder = mocker.patch.object(probe, "maple_ign_finder")
    binds = mocker.patch.object(probe, "key_binds", return_value={"x": "x"})

    assert probe.main(["keys", "--ign", "Bob"]) == 0

    binds.assert_called_once_with("Bob")
    finder.assert_not_called()


def test_keys_for_an_unknown_ign_is_an_error(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "maple_ign_finder", return_value="Nobody")
    mocker.patch.object(probe, "key_binds", side_effect=AssertionError("no section"))

    assert probe.main(["keys"]) == 1

    assert "Nobody" in capsys.readouterr().err
