"""
`configs/factory.toml` (#218): the caps the maintainer owns.

A wrong value must stop the loop with the key named, never run with a guess:
a typo'd cap that silently falls back to a default is a cap nobody set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from factory.config import CONFIG_PATH, Config, ConfigError, load, read
from factory.exit_codes import ExitCode

REPO_ROOT = Path(__file__).resolve().parents[2]

GOOD = """
attempts = 2
cycles = 2
wip = 1
launcher = "herdr"
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "factory.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_the_shipped_file_loads_with_the_decided_caps() -> None:
    config = load(REPO_ROOT / CONFIG_PATH)
    assert (config.attempts, config.cycles, config.wip) == (2, 2, 1)
    assert config.launcher == "herdr"


def test_the_two_timing_keys_are_optional(tmp_path: Path) -> None:
    config = load(_write(tmp_path, GOOD))
    assert config == Config(attempts=2, cycles=2, wip=1, launcher="herdr")
    assert config.worker_timeout_min is None
    assert config.poll_s is None


def test_the_two_timing_keys_are_read_when_present(tmp_path: Path) -> None:
    config = load(_write(tmp_path, GOOD + "worker_timeout_min = 30\npoll_s = 2.5\n"))
    assert (config.worker_timeout_min, config.poll_s) == (30, 2.5)


@pytest.mark.parametrize("key", ["attempts", "cycles", "wip", "launcher"])
def test_a_missing_required_key_names_the_key(tmp_path: Path, key: str) -> None:
    text = "\n".join(line for line in GOOD.splitlines() if not line.startswith(key))
    with pytest.raises(ConfigError, match=key):
        load(_write(tmp_path, text))


@pytest.mark.parametrize("key", ["attempts", "cycles", "wip"])
@pytest.mark.parametrize("bad", ["0", "-1", "1.5", '"2"', "true"])
def test_a_cap_must_be_a_positive_integer(tmp_path: Path, key: str, bad: str) -> None:
    """`true` is an int in Python, which is why it is named here."""
    text = GOOD.replace(f"{key} = ", f"{key} = {bad}\n#")
    with pytest.raises(ConfigError, match=key):
        load(_write(tmp_path, text))


@pytest.mark.parametrize("bad", ["3", "true", '""'])
def test_the_launcher_must_be_a_non_empty_string(tmp_path: Path, bad: str) -> None:
    with pytest.raises(ConfigError, match="launcher"):
        load(_write(tmp_path, GOOD.replace('"herdr"', bad)))


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("worker_timeout_min", "0"),
        ("worker_timeout_min", "1.5"),
        ("worker_timeout_min", '"30"'),
        ("poll_s", "0"),
        ("poll_s", "-1"),
        ("poll_s", "true"),
        ("poll_s", '"2"'),
    ],
)
def test_a_timing_key_that_is_present_must_be_valid(
    tmp_path: Path, key: str, bad: str
) -> None:
    with pytest.raises(ConfigError, match=key):
        load(_write(tmp_path, f"{GOOD}{key} = {bad}\n"))


def test_an_unknown_key_is_an_error_and_is_named(tmp_path: Path) -> None:
    """`attemps` is the real case: a typo that would otherwise change nothing."""
    with pytest.raises(ConfigError, match="attemps"):
        load(_write(tmp_path, GOOD + "attemps = 3\n"))


def test_a_missing_file_and_broken_toml_are_config_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="factory.toml"):
        load(tmp_path / "factory.toml")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load(_write(tmp_path, "attempts = = 2"))


def test_a_config_error_needs_a_human() -> None:
    """Exit 3: the maintainer's file is wrong, and a re-run will not fix it."""
    assert ConfigError.exit_code == ExitCode.NEEDS_HUMAN


def test_read_takes_the_session_s_own_checkout(tmp_path: Path) -> None:
    """Like the model table, so a ticket branch cannot raise its own caps."""
    (tmp_path / "configs").mkdir()
    (tmp_path / CONFIG_PATH).write_text(GOOD.replace("= 2", "= 5"), encoding="utf-8")
    assert read(tmp_path).attempts == 5


def test_v1_routing_never_reads_the_config() -> None:
    source = (REPO_ROOT / "factory" / "routing.py").read_text(encoding="utf-8")
    assert "factory.config" not in source
    assert "factory.toml" not in source
