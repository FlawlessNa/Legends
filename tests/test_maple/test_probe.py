import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest
from pytest_mock import MockerFixture

from botting.screen import Frame, MultipleWindows, WindowNotFound
from botting.utilities import Box
from maple import probe

HANDLE = 4242
READERS = probe.readers  # before any fixture mocks it
# Each pixel's value says where it is, so a crop can be checked by its corner.
PIXELS = np.zeros((306, 412, 3), dtype=np.uint8)
PIXELS[:, :, 0] = np.arange(412)[None, :] % 256
PIXELS[:, :, 1] = np.arange(306)[:, None] % 256


def frame(ok: bool = True, reason: str = "") -> Frame:
    return Frame(PIXELS, (412, 306), 1.0, True, ok, reason)


@pytest.fixture
def shot(
    mocker: MockerFixture, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> MagicMock:
    """Mocks the window, the capture and the output folder; returns the grab mock."""
    monkeypatch.setattr(probe, "PROBE_DIR", tmp_path / "probe")
    monkeypatch.setattr(probe, "GRAB_TIMEOUT", 0.0)
    mocker.patch.object(probe, "find_client", return_value=HANDLE)
    source = MagicMock()
    source.grab.return_value = frame()
    mocker.patch.object(probe, "frame_source", return_value=source)
    mocker.patch.object(probe, "readers", return_value=MagicMock())
    return source.grab


def _out(capsys: pytest.CaptureFixture[str]) -> dict:
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    return json.loads(lines[0])


def _png(capsys_out: dict, root: Path) -> np.ndarray:
    name = Path(capsys_out["path"]).name
    image = cv2.imread(str(root / "probe" / name))
    assert image is not None
    return image


# --- sources ----------------------------------------------------------------


def test_no_flag_writes_the_whole_frame(
    shot: MagicMock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert probe.main(["screenshot"]) == 0

    shot.assert_called_once_with(HANDLE)
    out = _out(capsys)
    assert (out["ok"], out["w"], out["h"]) == (True, 412, 306)
    assert out["path"].endswith("_window.png")
    assert (_png(out, tmp_path) == PIXELS).all()


def test_a_region_crops_the_box_its_reader_found(
    shot: MagicMock,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    found = Box(left=10, right=50, top=20, bottom=60)
    finder = MagicMock(return_value=found)
    mocker.patch.dict(probe.REGIONS, {"minimap": finder})

    assert probe.main(["screenshot", "--region", "minimap"]) == 0

    assert finder.call_args.args[1] is shot.return_value
    out = _out(capsys)
    assert out["path"].endswith("_minimap.png")
    assert (out["w"], out["h"]) == (40, 40)
    assert (_png(out, tmp_path) == PIXELS[20:60, 10:50]).all()


def test_a_box_is_frame_pixels_with_no_margin(
    shot: MagicMock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert probe.main(["screenshot", "--box", "5,6,100,50"]) == 0

    out = _out(capsys)
    assert out["path"].endswith("_box.png")
    assert (_png(out, tmp_path) == PIXELS[6:50, 5:100]).all()


def test_region_and_box_together_are_a_usage_error(shot: MagicMock) -> None:
    with pytest.raises(SystemExit) as raised:
        probe.main(["screenshot", "--region", "hp", "--box", "0,0,10,10"])

    assert raised.value.code == 2
    shot.assert_not_called()


@pytest.mark.parametrize("region", ["ign", "job", "inventory", "chat", "hp_bar"])
def test_regions_without_a_reader_are_gone(shot: MagicMock, region: str) -> None:
    with pytest.raises(SystemExit) as raised:
        probe.main(["screenshot", "--region", region])

    assert raised.value.code == 2


@pytest.mark.parametrize(
    "box", ["1,2,3", "a,b,c,d", "10,0,5,5", "0,10,5,5", "-1,0,5,5"]
)
def test_a_malformed_box_is_a_usage_error(shot: MagicMock, box: str) -> None:
    with pytest.raises(SystemExit) as raised:
        probe.main(["screenshot", "--box", box])

    assert raised.value.code == 2
    shot.assert_not_called()


def test_a_box_outside_the_frame_writes_nothing(
    shot: MagicMock, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert probe.main(["screenshot", "--box", "0,0,413,50"]) == 1

    assert "outside" in capsys.readouterr().err
    assert not (tmp_path / "probe").exists()


# --- a frame that isn't ok --------------------------------------------------


@pytest.mark.parametrize(
    "argv", [["screenshot"], ["screenshot", "--region", "minimap"], ["regions"]]
)
def test_a_frame_that_is_not_ok_is_refused_with_its_reason_and_writes_nothing(
    shot: MagicMock,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    argv: list[str],
) -> None:
    shot.return_value = frame(ok=False, reason="window 4242 wasn't in front")

    code = probe.main(argv)

    captured = capsys.readouterr()
    assert code == probe.EXIT_FRAME_NOT_OK
    assert "window 4242 wasn't in front" in captured.err
    assert captured.out == ""
    assert not (tmp_path / "probe").exists()


def test_a_frame_that_is_not_ok_at_first_is_asked_for_again(
    shot: MagicMock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A new process's first copy can be empty when the screen hasn't changed."""
    monkeypatch.setattr(probe, "GRAB_TIMEOUT", 5.0)
    monkeypatch.setattr(probe, "GRAB_POLL", 0.0)
    empty = "no frame of this client rectangle has been copied yet"
    shot.side_effect = [frame(ok=False, reason=empty), frame()]

    assert probe.main(["screenshot"]) == 0

    assert shot.call_count == 2
    assert _out(capsys)["w"] == 412


# --- a missing region -------------------------------------------------------


def test_a_region_that_is_not_showing_exits_3_with_why_and_writes_nothing(
    shot: MagicMock,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch.dict(
        probe.REGIONS, {"buffs": lambda readers, frame: "no buff slot found"}
    )

    code = probe.main(["screenshot", "--region", "buffs"])

    captured = capsys.readouterr()
    assert code == probe.EXIT_NOT_SHOWING
    assert "buffs" in captured.err
    assert "no buff slot found" in captured.err
    assert captured.out == ""
    assert not (tmp_path / "probe").exists()


def test_a_region_without_the_game_data_is_an_error_that_says_so(
    shot: MagicMock,
    mocker: MockerFixture,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    mocker.patch.object(probe, "readers", wraps=READERS.__wrapped__)
    mocker.patch.object(
        probe,
        "load_reader_sprites",
        side_effect=probe.StartupRefused("run `python -m game_data extract`"),
    )

    assert probe.main(["screenshot", "--region", "hp"]) == probe.EXIT_ERROR

    assert "game_data extract" in capsys.readouterr().err
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


def test_the_window_is_found_by_class_and_executable_not_by_ign(
    shot: MagicMock, mocker: MockerFixture
) -> None:
    find = mocker.patch.object(probe, "find_client", return_value=77)

    assert probe.main(["screenshot"]) == 0

    find.assert_called_once_with()
    shot.assert_called_once_with(77)


def test_no_client_open_exits_4(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "find_client", side_effect=WindowNotFound("none"))

    assert probe.main(["screenshot"]) == probe.EXIT_NO_CLIENT

    assert "none" in capsys.readouterr().err
    shot.assert_not_called()


def test_several_clients_exit_5(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(
        probe, "find_client", side_effect=MultipleWindows("handles [1, 2]")
    )

    assert probe.main(["screenshot"]) == probe.EXIT_SEVERAL_CLIENTS

    assert "handles [1, 2]" in capsys.readouterr().err
    shot.assert_not_called()


# --- regions and keys -------------------------------------------------------


def test_regions_gives_each_box_or_null_from_one_frame(
    shot: MagicMock, mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.dict(
        probe.REGIONS,
        {
            "hp": lambda r, f: Box(left=1, right=3, top=2, bottom=4),
            "minimap": lambda r, f: "minimap absent",
        },
        clear=True,
    )

    assert probe.main(["regions"]) == 0

    assert _out(capsys) == {
        "ok": True,
        "regions": {"hp": [1, 2, 3, 4], "minimap": None},
    }
    shot.assert_called_once_with(HANDLE)


def test_the_regions_are_those_the_screen_readers_give() -> None:
    assert list(probe.REGIONS) == [
        "status_bar",
        "level",
        "hp",
        "mp",
        "exp",
        "minimap",
        "buffs",
    ]


def test_keys_uses_the_only_keybindings_section(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "_binding_sections", return_value=["Alice"])
    binds = mocker.patch.object(
        probe, "key_binds", return_value={"inventory menu": "i", "attack": "a"}
    )
    find = mocker.patch.object(probe, "find_client")

    assert probe.main(["keys"]) == 0

    binds.assert_called_once_with("Alice")
    find.assert_not_called()
    assert _out(capsys) == {
        "ok": True,
        "ign": "Alice",
        "keys": ["attack", "inventory menu"],
    }


def test_keys_with_ign_reads_that_section(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "_binding_sections", return_value=["Alice", "Bob"])
    binds = mocker.patch.object(probe, "key_binds", return_value={"x": "x"})

    assert probe.main(["keys", "--ign", "Bob"]) == 0

    binds.assert_called_once_with("Bob")


def test_keys_with_several_sections_and_no_ign_asks_for_one(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "_binding_sections", return_value=["Alice", "Bob"])

    assert probe.main(["keys"]) == probe.EXIT_ERROR

    err = capsys.readouterr().err
    assert "--ign" in err
    assert "Bob" in err


def test_keys_for_an_unknown_ign_is_an_error(
    mocker: MockerFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    mocker.patch.object(probe, "key_binds", side_effect=AssertionError("no section"))

    assert probe.main(["keys", "--ign", "Nobody"]) == probe.EXIT_ERROR

    assert "Nobody" in capsys.readouterr().err
