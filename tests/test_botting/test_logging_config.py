"""
Tests for the dictConfig half of `botting.logging_config`: Log Bucket routing,
the Console Threshold dial, and the guarantee that one record reaches every
sink it belongs in.

The load-bearing test here is `test_a_record_lands_in_exactly_one_bucket_file`.
A `QueueListener` hands the *same* `LogRecord` object to each handler in turn,
so a formatter that rewrote `record.name` in place would strip the `botting.`
prefix the next handler's `BucketFilter` matches on - and every handler after
the first would silently drop the record. Nothing else catches that.

No Session and no game client is started. Child-process records are pushed
through a real `QueueHandler`/`QueueListener` pair rather than a spawned
process, because the queue *is* the whole of what a child process contributes
to this path.
"""

import logging
import logging.config
import logging.handlers
import queue

import pytest

from botting.logging_config import (
    BUCKET_NAMES,
    CONSOLE_DEFAULT,
    ConsoleFilter,
    CustomFormatter,
    PARENT_LOG,
    _env_overrides,
    bucket_for,
    full_config,
    levels_config,
)
from botting.telemetry import emit_event
from botting.utilities import setup_child_proc_logging

MOVEMENT_LOGGER = f"{PARENT_LOG}.maple.decision_makers.rotation"
DECISIONS_LOGGER = f"{PARENT_LOG}.core.engine"


@pytest.fixture
def session_dir(tmp_path):
    """
    A Session directory with the full handler set configured against it.

    Restores the parent logger's own configuration afterwards, since
    `dictConfig` replaces its handler list outright.
    """
    parent = logging.getLogger(PARENT_LOG)
    saved_handlers, saved_level, saved_propagate = (
        parent.handlers[:],
        parent.level,
        parent.propagate,
    )
    logging.config.dictConfig(full_config(tmp_path))
    yield tmp_path
    for handler in parent.handlers[:]:
        parent.removeHandler(handler)
        handler.close()
    parent.handlers[:] = saved_handlers
    parent.setLevel(saved_level)
    parent.propagate = saved_propagate


def read(session_dir, name: str) -> list[str]:
    """:return: The lines of one log file, or [] if it was never written to."""
    for handler in logging.getLogger(PARENT_LOG).handlers:
        handler.flush()
    path = session_dir / f"{name}.log"
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


# --- Bucket routing ---------------------------------------------------------


@pytest.mark.parametrize(
    "name, bucket",
    [
        (PARENT_LOG, "other"),
        (f"{PARENT_LOG}.communications.discord_comm", "other"),
        (f"{PARENT_LOG}.controller.high_level", "inputs"),
        (f"{PARENT_LOG}.core.engine", "decisions"),
        (f"{PARENT_LOG}.maple.bots.training", "decisions"),
        (f"{PARENT_LOG}.maple.decision_makers.rebuffs", "decisions"),
        # Three decision_makers submodules escape their parent's bucket - the
        # reason routing is longest-prefix rather than first-match.
        (f"{PARENT_LOG}.maple.decision_makers.rotation", "movement"),
        (f"{PARENT_LOG}.maple.decision_makers.mixins._map_mixins", "movement"),
        (f"{PARENT_LOG}.maple.decision_makers.mixins._rotation_mixins", "movement"),
        (f"{PARENT_LOG}.maple.model.mechanics.movement_mechanics_v2", "movement"),
        (f"{PARENT_LOG}.maple.actions.movements_v2", "movement"),
        # ...while its siblings under maple.actions are not movement.
        (f"{PARENT_LOG}.maple.actions.menus", "other"),
    ],
)
def test_bucket_for_routes_on_the_longest_matching_prefix(name, bucket):
    assert bucket_for(name) == bucket


def test_a_prefix_only_matches_on_a_dotted_boundary():
    """`botting.core` must not claim `botting.core_utils`."""
    assert bucket_for(f"{PARENT_LOG}.core_utils.thing") == "other"


def test_an_unknown_name_falls_back_to_other():
    assert bucket_for("some.foreign.library") == "other"


# --- One record, every sink it belongs in -----------------------------------


def test_a_record_lands_in_exactly_one_bucket_file_and_in_session_log(session_dir):
    """
    The regression guard for the formatter's in-place record mutation.

    Records arrive from a child process the way production delivers them - off
    the queue, one object handed to every handler in turn.
    """
    log_queue: queue.Queue = queue.Queue()
    listener = logging.handlers.QueueListener(
        log_queue,
        *logging.getLogger(PARENT_LOG).handlers,
        respect_handler_level=True,
    )
    producer = logging.getLogger(MOVEMENT_LOGGER)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    producer.addHandler(queue_handler)
    # In a child process the queue is the only way out: that process' `botting`
    # logger owns no file handlers. Cutting propagation here reproduces that,
    # rather than letting the record reach the same handlers twice.
    producer.propagate = False
    listener.start()
    try:
        producer.warning("from the child")
    finally:
        listener.stop()
        producer.removeHandler(queue_handler)
        producer.propagate = True

    assert len(read(session_dir, "movement")) == 1
    assert [b for b in BUCKET_NAMES if read(session_dir, b)] == ["movement"]
    assert len(read(session_dir, "session")) == 1


def test_every_bucket_gets_its_own_file(session_dir):
    logging.getLogger(MOVEMENT_LOGGER).warning("moved")
    logging.getLogger(DECISIONS_LOGGER).warning("decided")

    assert len(read(session_dir, "movement")) == 1
    assert len(read(session_dir, "decisions")) == 1
    assert read(session_dir, "inputs") == []
    # The combined file is the one place the interleaving survives.
    assert len(read(session_dir, "session")) == 2


def test_files_capture_below_the_console_threshold(session_dir):
    """
    Capture and display are two dials. A DEBUG record is invisible on the
    console at the default threshold and still lands in both files - which is
    exactly what the NOTSET rows of the sweep turned into.
    """
    logging.getLogger(MOVEMENT_LOGGER).debug("quiet")

    assert len(read(session_dir, "movement")) == 1
    assert len(read(session_dir, "session")) == 1


def test_telemetry_records_never_reach_a_text_file(session_dir):
    """
    A Telemetry Record carries an empty message, so a text handler missing the
    `not_telemetry` filter contributes one blank line per emitted event.
    """
    emit_event("cid-1", "tick", {"a": 1}, logger_name=MOVEMENT_LOGGER)

    assert read(session_dir, "movement") == []
    assert read(session_dir, "session") == []


# --- The formatter ----------------------------------------------------------


def test_the_formatter_leaves_the_record_untouched():
    record = logging.LogRecord(
        MOVEMENT_LOGGER, logging.WARNING, __file__, 1, "hello", None, None
    )
    before = dict(record.__dict__)

    CustomFormatter(fmt="{name}:::{message}", style="{").format(record)

    assert record.__dict__ == before


def test_the_formatter_strips_the_prefix_before_padding():
    """
    Padding first and stripping after leaves each record padded to a different
    width, which is what made the console and the file disagree.
    """
    record = logging.LogRecord(
        f"{PARENT_LOG}.core.engine", logging.WARNING, __file__, 1, "hi", None, None
    )

    line = CustomFormatter(fmt="{name}|", style="{").format(record)

    assert line == "engine".ljust(50) + "|"


def test_the_formatter_names_the_task_even_outside_one():
    record = logging.LogRecord(
        MOVEMENT_LOGGER, logging.WARNING, __file__, 1, "hi", None, None
    )
    record.taskName = None

    line = CustomFormatter(fmt="{taskName}|", style="{").format(record)

    assert line == "-".ljust(30) + "|"


# --- The display dial -------------------------------------------------------


def make_record(name: str, level: int) -> logging.LogRecord:
    return logging.LogRecord(name, level, __file__, 1, "m", None, None)


def test_an_empty_threshold_map_reproduces_todays_console():
    """
    The seed that makes the sweep reviewable: everything at INFO and above is
    shown, everything below is not.
    """
    console = ConsoleFilter()

    assert console.filter(make_record(MOVEMENT_LOGGER, CONSOLE_DEFAULT))
    assert not console.filter(make_record(MOVEMENT_LOGGER, logging.DEBUG))


def test_env_var_turns_one_bucket_up(monkeypatch):
    monkeypatch.setenv("BOTTING_CONSOLE", "movement=DEBUG")
    console = ConsoleFilter()

    assert console.filter(make_record(MOVEMENT_LOGGER, logging.DEBUG))
    # Only that bucket: everything else keeps the default.
    assert not console.filter(make_record(DECISIONS_LOGGER, logging.DEBUG))


def test_env_var_mutes_a_prefix(monkeypatch):
    monkeypatch.setenv("BOTTING_CONSOLE", f"{DECISIONS_LOGGER}=OFF")
    console = ConsoleFilter()

    assert not console.filter(make_record(DECISIONS_LOGGER, logging.CRITICAL))
    assert console.filter(make_record(MOVEMENT_LOGGER, logging.INFO))


def test_an_unknown_level_name_is_rejected(monkeypatch):
    monkeypatch.setenv("BOTTING_CONSOLE", "movement=LOUD")

    with pytest.raises(ValueError, match="LOUD"):
        _env_overrides()


def test_the_display_dial_cannot_cost_file_fidelity(monkeypatch, tmp_path):
    """
    `BOTTING_CONSOLE` is console-only by construction: no file handler carries
    the ConsoleFilter, so muting a prefix cannot silence its log files.
    """
    monkeypatch.setenv("BOTTING_CONSOLE", f"{MOVEMENT_LOGGER}=OFF")
    config = full_config(tmp_path)

    for name, handler in config["handlers"].items():
        assert ("console" in handler["filters"]) == (name == "console")


# --- The capture dial -------------------------------------------------------


def test_levels_config_declares_no_handlers():
    """
    It is applied in every process, including the children - which have no
    business owning a file.
    """
    config = levels_config()

    assert "handlers" not in config
    assert config["loggers"][PARENT_LOG] == {"level": "DEBUG", "propagate": False}


def test_every_text_handler_filters_telemetry_out(tmp_path):
    config = full_config(tmp_path)

    for handler in config["handlers"].values():
        assert "not_telemetry" in handler["filters"]


# --- The child-process end of the queue -------------------------------------


@pytest.fixture
def isolated_loggers():
    """
    Save and restore both `botting` and the root logger.

    `setup_child_proc_logging` rewrites the parent logger's handler list in
    place, and one test below deliberately puts a handler on the root logger.
    """
    parent, root = logging.getLogger(PARENT_LOG), logging.getLogger()
    saved = [(lg, lg.handlers[:], lg.propagate) for lg in (parent, root)]
    yield parent, root
    for lg, handlers, propagate in saved:
        lg.handlers[:] = handlers
        lg.propagate = propagate


def test_setup_child_proc_logging_installs_one_queue_handler(isolated_loggers):
    parent, _ = isolated_loggers
    q = queue.Queue()

    setup_child_proc_logging(q)

    assert len(parent.handlers) == 1
    handler = parent.handlers[0]
    assert isinstance(handler, logging.handlers.QueueHandler)
    assert handler.queue is q

    parent.error("from the child %s", "process")
    assert q.get_nowait().getMessage() == "from the child process"


def test_setup_child_proc_logging_closes_the_handlers_it_drops(isolated_loggers):
    """A child inherits no file of its own; whatever was attached is shut."""
    parent, _ = isolated_loggers
    closed = []
    stale = logging.NullHandler()
    stale.close = lambda: closed.append(stale)
    parent.addHandler(stale)

    setup_child_proc_logging(queue.Queue())

    assert closed == [stale]
    assert stale not in parent.handlers


def test_setup_child_proc_logging_ignores_handlers_further_up(isolated_loggers):
    """
    Regression test. The loop this replaces was `while root.hasHandlers()`,
    which walks *up* the hierarchy: with `botting` handler-less, propagating,
    and the root logger holding a handler, it saw a handler that was never in
    `botting.handlers` and raised IndexError on a list that never shrank. Only
    `levels_config()`'s `propagate: False`, set in another module, kept it from
    firing in production.
    """
    parent, root = isolated_loggers
    parent.handlers[:] = []
    parent.propagate = True
    root_handler = logging.NullHandler()
    root.addHandler(root_handler)

    setup_child_proc_logging(queue.Queue())

    assert [type(h) for h in parent.handlers] == [logging.handlers.QueueHandler]
    # The root logger is somebody else's; the child must not have touched it.
    assert root_handler in root.handlers
