"""
Tests for the Telemetry Record stream: the envelope `emit_event` produces, the
JSONL sink it reaches, and the separation between telemetry and the text logs.

Nothing here starts a Session or a game client. The cross-process path is
exercised by pickling a record rather than spawning a process, because what the
`QueueHandler` transport actually requires of a Telemetry Record is that it
survives the pickle.
"""

import json
import logging
import logging.handlers
import multiprocessing
import pickle
import queue

import pytest

from botting import telemetry
from botting.core.decision_maker import DecisionMaker
from botting.logging_config import (
    KEEP_SESSIONS,
    PARENT_LOG,
    new_session_dir,
    prune_old_sessions,
)
from botting.telemetry import (
    TELEMETRY_ATTR,
    TelemetryHandler,
    emit_event,
    is_telemetry,
    not_telemetry,
)

LOGGER_NAME = f"{PARENT_LOG}.tests.telemetry"


@pytest.fixture
def sink(tmp_path):
    """
    A TelemetryHandler attached to the project's parent logger, with a reader.

    Attaching to `PARENT_LOG` is what production does, and it is the only way
    the hierarchy walk from an arbitrary Producer logger reaches the sink.

    :return: A zero-argument callable returning the decoded records written so
        far.
    """
    path = tmp_path / "telemetry.jsonl"
    handler = TelemetryHandler(path)
    parent = logging.getLogger(PARENT_LOG)
    parent.addHandler(handler)

    def _records() -> list[dict]:
        handler.flush()
        if not path.exists():
            return []
        return [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]

    yield _records
    parent.removeHandler(handler)
    handler.close()


# --- The envelope -----------------------------------------------------------


def test_emit_event_writes_one_line_per_record(sink):
    emit_event("cid-1", "decided", {"a": 1}, logger_name=LOGGER_NAME)
    emit_event("cid-2", "decided", {"a": 2}, logger_name=LOGGER_NAME)

    assert len(sink()) == 2


def test_envelope_carries_the_five_agreed_fields(sink):
    emit_event("cid-1", "movement_predicted", {"target": [3, 4]}, LOGGER_NAME)

    (record,) = sink()
    assert set(record) == {
        "timestamp",
        "correlation_id",
        "logger_name",
        "event_type",
        "payload",
    }
    assert record["correlation_id"] == "cid-1"
    assert record["logger_name"] == LOGGER_NAME
    assert record["event_type"] == "movement_predicted"
    assert record["payload"] == {"target": [3, 4]}


def test_absent_correlation_id_is_recorded_as_null(sink):
    """A record no decision caused says so, rather than inventing an id."""
    emit_event(None, "session_started", logger_name=LOGGER_NAME)

    (record,) = sink()
    assert record["correlation_id"] is None


def test_omitted_payload_becomes_an_empty_object(sink):
    emit_event("cid-1", "tick", logger_name=LOGGER_NAME)

    assert sink()[0]["payload"] == {}


def test_logger_name_defaults_when_the_producer_names_none(sink):
    emit_event("cid-1", "tick")

    assert sink()[0]["logger_name"] == telemetry.DEFAULT_LOGGER_NAME


def test_timestamp_is_iso_8601_with_an_offset(sink):
    import datetime

    emit_event("cid-1", "tick", logger_name=LOGGER_NAME)

    parsed = datetime.datetime.fromisoformat(sink()[0]["timestamp"])
    assert parsed.tzinfo is not None


# --- Payload robustness -----------------------------------------------------


def test_unserialisable_value_falls_back_to_repr(sink):
    """Telemetry must never take down the thing it observes."""

    class Opaque:
        def __repr__(self) -> str:
            return "<Opaque>"

    emit_event("cid-1", "tick", {"thing": Opaque()}, LOGGER_NAME)

    assert sink()[0]["payload"] == {"thing": "<Opaque>"}


def test_unserialisable_key_degrades_the_payload_but_keeps_the_record(sink):
    emit_event("cid-1", "tick", {(1, 2): "tuple key"}, LOGGER_NAME)

    (record,) = sink()
    assert record["correlation_id"] == "cid-1"
    assert record["event_type"] == "tick"
    assert "telemetry_encode_error" in record["payload"]
    assert "tuple key" in record["payload"]["payload_repr"]


def test_reference_cycle_degrades_the_payload_but_keeps_the_record(sink):
    payload: dict = {}
    payload["self"] = payload

    emit_event("cid-1", "tick", payload, LOGGER_NAME)

    (record,) = sink()
    assert record["correlation_id"] == "cid-1"
    assert "telemetry_encode_error" in record["payload"]


# --- Telemetry is not a log line --------------------------------------------


def test_telemetry_records_are_kept_off_text_handlers(sink, tmp_path):
    text_path = tmp_path / "text.log"
    text_handler = logging.FileHandler(text_path, encoding="utf-8")
    text_handler.addFilter(not_telemetry)
    parent = logging.getLogger(PARENT_LOG)
    parent.addHandler(text_handler)
    try:
        emit_event("cid-1", "tick", logger_name=LOGGER_NAME)
        logging.getLogger(LOGGER_NAME).warning("narrative")
        text_handler.flush()
    finally:
        parent.removeHandler(text_handler)
        text_handler.close()

    assert text_path.read_text(encoding="utf-8").splitlines() == ["narrative"]


def test_the_sink_admits_only_telemetry(sink):
    """The handler filters on the marker itself, not on how it was wired up."""
    logging.getLogger(LOGGER_NAME).warning("narrative")

    assert sink() == []


def test_emitting_is_not_suppressible_by_logger_level(sink):
    """
    Capture is total: a Telemetry Record's level describes the transport, not
    the event, so raising a logger's level must not lose records.
    """
    producer = logging.getLogger(LOGGER_NAME)
    producer.setLevel(logging.CRITICAL)
    try:
        emit_event("cid-1", "tick", logger_name=LOGGER_NAME)
    finally:
        producer.setLevel(logging.NOTSET)

    assert len(sink()) == 1


# --- The child-process transport --------------------------------------------


def test_a_telemetry_record_survives_the_pickle_the_queue_requires():
    """
    Child processes reach the sink through a `QueueHandler`, which pickles the
    record. Serialising the envelope at emit time is what makes that safe
    regardless of what the payload held.
    """
    log_queue: queue.Queue = queue.Queue()
    producer = logging.getLogger(LOGGER_NAME)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    producer.addHandler(queue_handler)
    try:
        emit_event("cid-1", "tick", {"unpicklable": lambda: None}, LOGGER_NAME)
    finally:
        producer.removeHandler(queue_handler)

    record = log_queue.get_nowait()
    round_tripped = pickle.loads(pickle.dumps(record))

    assert is_telemetry(round_tripped)
    assert json.loads(getattr(round_tripped, TELEMETRY_ATTR))["correlation_id"] == (
        "cid-1"
    )


def test_a_record_from_a_queue_reaches_the_sink(sink):
    """The full child-process path: QueueHandler -> QueueListener -> sink."""
    log_queue = multiprocessing.Queue()
    producer = logging.getLogger(LOGGER_NAME)
    queue_handler = logging.handlers.QueueHandler(log_queue)
    producer.addHandler(queue_handler)
    try:
        emit_event("cid-1", "tick", {"a": 1}, LOGGER_NAME)
    finally:
        producer.removeHandler(queue_handler)

    listener = logging.handlers.QueueListener(
        log_queue,
        *logging.getLogger(PARENT_LOG).handlers,
        respect_handler_level=True,
    )
    listener.start()
    listener.stop()

    assert sink()[0]["payload"] == {"a": 1}


# --- DecisionMaker.emit() ---------------------------------------------------


class _Producer(DecisionMaker):
    """A DecisionMaker that only exists to be a Producer."""

    async def _decide(self, *args, **kwargs) -> None:  # pragma: no cover
        pass


@pytest.fixture
def producer(mocker) -> DecisionMaker:
    """A `_Producer` with its shared-proxy machinery stubbed out."""
    mocker.patch(
        "botting.core.decision_maker.ProxyFactory", return_value=mocker.MagicMock()
    )
    return _Producer(mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock())


def test_decision_maker_emit_closes_over_the_correlation_id(sink, producer):
    producer.correlation_id = "cid-42"

    producer.emit("decided", {"why": "mob spotted"})

    (record,) = sink()
    assert record["correlation_id"] == "cid-42"
    assert record["event_type"] == "decided"
    assert record["payload"] == {"why": "mob spotted"}


def test_decision_maker_emit_before_any_decide_carries_no_correlation_id(
    sink, producer
):
    producer.emit("constructed")

    assert sink()[0]["correlation_id"] is None


def _producer_declared_in(module: str, mocker) -> DecisionMaker:
    """
    A `_Producer` carrying the `__module__` a DecisionMaker declared in `module`
    would have. Set before construction, which is when emit()'s logger name is
    derived.
    """
    mocker.patch(
        "botting.core.decision_maker.ProxyFactory", return_value=mocker.MagicMock()
    )

    class _Declared(_Producer):
        pass

    _Declared.__module__ = module
    return _Declared(mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock())


def test_a_botting_decision_maker_is_attributed_to_its_own_module(sink, mocker):
    """`botting.*` modules name their logger after `__name__`, unprefixed."""
    producer = _producer_declared_in("botting.core.decision_maker", mocker)

    producer.emit("tick")

    assert sink()[0]["logger_name"] == "botting.core.decision_maker"


def test_a_maple_decision_maker_is_attributed_under_the_parent_logger(sink, mocker):
    """`maple.*` modules prefix `__name__` with PARENT_LOG; emit() must match."""
    producer = _producer_declared_in("maple.decision_makers.rotation", mocker)

    producer.emit("tick")

    assert sink()[0]["logger_name"] == "botting.maple.decision_makers.rotation"


# --- The Session directory --------------------------------------------------


def test_new_session_dir_creates_a_timestamped_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("botting.logging_config.LOGS_ROOT", tmp_path / "logs")

    session_dir = new_session_dir()

    assert session_dir.is_dir()
    assert session_dir.parent == tmp_path / "logs"


def test_pruning_keeps_room_for_the_session_about_to_start(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    monkeypatch.setattr("botting.logging_config.LOGS_ROOT", logs_root)
    for i in range(KEEP_SESSIONS + 5):
        (logs_root / f"2026-01-01_00-00-{i:02d}").mkdir()

    prune_old_sessions()

    assert len(list(logs_root.iterdir())) == KEEP_SESSIONS - 1


def test_pruning_drops_the_oldest_first(monkeypatch, tmp_path):
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    monkeypatch.setattr("botting.logging_config.LOGS_ROOT", logs_root)
    for i in range(4):
        (logs_root / f"2026-01-01_00-00-{i:02d}").mkdir()

    prune_old_sessions(keep=3)

    assert sorted(p.name for p in logs_root.iterdir()) == [
        "2026-01-01_00-00-02",
        "2026-01-01_00-00-03",
    ]


def test_pruning_leaves_legacy_log_files_alone(monkeypatch, tmp_path):
    """Legacy `Session YYYYMMDD.log` files sit at the logs root as files."""
    logs_root = tmp_path / "logs"
    logs_root.mkdir()
    monkeypatch.setattr("botting.logging_config.LOGS_ROOT", logs_root)
    (logs_root / "Session 20250101.log").write_text("legacy", encoding="utf-8")

    prune_old_sessions(keep=1)

    assert (logs_root / "Session 20250101.log").exists()
