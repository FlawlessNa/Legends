"""
`ChatReplies`: the chat's one DecisionMaker. It reads the chat, raises the
alarm on a GM's line, and answers players who talk to the character (#455).

**The alarm** comes first, on each line as it is read, and apart from
everything about replies: replies being off (`chat_replies: false`, `REPLIES
OFF`), the model being unreachable, or a reply in flight never delay or silence
it. A GM's line, and any later line of the same speaker, also stops training:
every other DecisionMaker of the bot is disabled (`_disable_decision_makers`)
until `RESUME` gives them back (`on_resume`, called by `Bot.resume`).

**Following the conversation.** Every cycle each line read is addressed
(`Addressing`) and appended to the `Conversation`. Lines on screen at the first
read were there before the session, so they are context, never answered.

**Replying**, one reply in flight at a time. The oldest pending `Burst` (a GM's
first) goes to the `Relay` as soon as it is pending; training goes on meanwhile.
The reply is sent no sooner than a read delay after its lines appeared: 2 s
plus 60 ms per character, jittered by 30 %, capped at 8 s (`read_delay`). The
model's latency is spent inside that delay; a model slower than it is sent at
once. The send is one `reply_in_chat` Action at `ANTI_DETECTION`, blocking
lower priorities and cancelling the training Actions in flight; `replies_on` is
read again just before it, so a takeover since the model answered cancels it.

**Our own reply's echo.** The Action's callback, in Main Process, puts the reply
on a queue once it is typed; the next cycle registers it with `expect_echo`.
Lines read while it is being typed are held until then, so its echo is always
known for ours, even when its speaker misreads.

**Limits.** One exchange with a player per 10 s (`PLAYER_INTERVAL`), counted
from when the last one ended; and 20 model calls per 10 minutes for the session
(`SESSION_CALLS`, D13). The call past that is not made: `chat.reply_limited` is
emitted and one Action releases every key, closes the game and ends the session
as `KILL` does, its Discord alert ringing the maintainer.

**Takeover.** `replies_on` (`REPLIES OFF`, a Discord `WRITE`) stops the
replies, not the reading: lines read then are context, posted to Discord as they
come, and lines left pending are given up, never answered late.

Speakers' names and messages are logged and posted to Discord, never put in an
event payload.
"""

import asyncio
import concurrent.futures
import logging
import multiprocessing.connection
import multiprocessing.managers
import queue
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import NoReturn, Protocol

from pydantic import BaseModel

from botting import PARENT_LOG, controller
from botting.controller import TypingPace
from botting.core import ActionRequest, BotData, DecisionMaker, DiscordRequest
from botting.llm import DEFAULT_MODEL_ID, AnthropicModel, ModelAnswer, StructuredModel
from botting.screen import ClientNotClosed, Reading, Status, close_client
from maple.actions import priorities, reply_in_chat
from maple.chat_replies.addressing import STRENGTH, Address, Addressing
from maple.chat_replies.conversation import Burst, Conversation, Entry, EntryState
from maple.chat_replies.instructions import InstructionsError, load_instructions
from maple.chat_replies.line import same_speaker
from maple.chat_replies.mirror import discord_mention, mirror, mirror_unanswered
from maple.chat_replies.relay import Failed, Relay, RelayOutcome, Reply, Silent
from maple.screen.chat import CHAT, ChatKind, ChatLine
from maple.screen.font import UNREAD
from maple.screen.sprites import StartupRefused
from maple.telemetry_events import (
    CHAT_GM_LINE,
    CHAT_LINE_ADDRESSED,
    CHAT_REPLY_FAILED,
    CHAT_REPLY_LIMITED,
    CHAT_REPLY_SENT,
    CHAT_REPLY_SILENT,
    ChatLinePayload,
    LineAddressedPayload,
    ReplyFailedPayload,
    ReplyLimitedPayload,
    ReplySentPayload,
    ReplySilentPayload,
)
from paths import ROOT

from .mixins import UIMixin

logger = logging.getLogger(f"{PARENT_LOG}.{__name__}")

DISCORD_CONFIG = Path(ROOT) / "configs" / "discord.ini"

READ_BASE = 2.0
"""Seconds a person takes to notice a line, before reading it."""
READ_PER_CHAR = 0.060
"""Seconds to read each character of it."""
READ_JITTER = 0.30
"""How far a read delay strays either way, as a fraction of it."""
READ_CAP = 8.0
"""The longest read delay, in seconds."""
PLAYER_INTERVAL = 10.0
"""Seconds between two exchanges with one player."""
SESSION_CALLS = 20
"""The most model calls in `SESSION_WINDOW`: the call past it ends the session."""
SESSION_WINDOW = 600.0
"""Seconds over which `SESSION_CALLS` is counted."""
ECHO_WAIT = 60.0
"""Seconds lines are held for a reply's echo before following the chat anyway,
should Main Process never say the reply was typed."""
TRAINING_ACTIONS = ("Rotation", "MobsHitting", "TelecastMobsHitting")
"""The DecisionMakers whose Actions in flight a reply cancels, as a Discord
`WRITE` does."""
CHANNELS: dict[ChatKind, str] = {
    ChatKind.GENERAL: "general",
    ChatKind.PARTY: "party",
    ChatKind.BUDDY: "buddy",
    ChatKind.WHISPER: "whisper",
    # Where a GM's own line is answered isn't known until GM lines are captured
    # (#482): on general, where a person would answer a GM who spoke on the map.
    ChatKind.GM: "general",
}
"""The channel `reply_in_chat` answers each kind of line on."""


class CheckedModel(StructuredModel, Protocol):
    """A model that can also say, before the session starts, whether it is reachable."""

    async def check(self) -> str | None: ...


def read_delay(chars: int, jitter: float) -> float:
    """
    The "notice and read" delay for a line of `chars` characters, in seconds.

    :param jitter: The factor it is multiplied by, drawn in
        `[1 - READ_JITTER, 1 + READ_JITTER]`.
    """
    return min(READ_CAP, (READ_BASE + READ_PER_CHAR * chars) * jitter)


class _CallLimit:
    """
    The model, counting the session's calls: at most `SESSION_CALLS` in any
    `SESSION_WINDOW`. The call past that is not made; it answers `error`, and
    `exceeded` is set for `ChatReplies` to end the session.
    """

    def __init__(self, model: StructuredModel, clock: Callable[[], float]) -> None:
        self._model = model
        self._clock = clock
        self._calls: list[float] = []
        self.exceeded = False

    def in_window(self) -> int:
        """The calls made in the last `SESSION_WINDOW`."""
        now = self._clock()
        self._calls = [t for t in self._calls if now - t < SESSION_WINDOW]
        return len(self._calls)

    async def ask(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        *,
        correlation_id: str | None = None,
    ) -> ModelAnswer:
        if self.in_window() >= SESSION_CALLS:
            self.exceeded = True
            return ModelAnswer("error", None, "the session's model call limit", 0)
        self._calls.append(self._clock())
        return await self._model.ask(
            system, user, schema, correlation_id=correlation_id
        )


@dataclass(frozen=True, slots=True)
class _Read:
    """A line read, waiting to be appended."""

    line: ChatLine
    address: Address
    at: float
    earlier: bool
    """On screen at the first read: said before the session."""


class ChatReplies(UIMixin, DecisionMaker):
    """Reads `chat_lines` every cycle: raises the alarm on a GM's line, and
    answers what is addressed to the character (module docstring)."""

    _throttle = 0.5
    screen_readers = (CHAT,)

    def __init__(
        self,
        metadata: multiprocessing.managers.DictProxy,
        data: BotData,
        pipe: multiprocessing.connection.Connection,
        chat_replies: bool = True,
        discord_config: Path = DISCORD_CONFIG,
        model_factory: Callable[[], CheckedModel] | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        rng: random.Random | None = None,
        **kwargs: object,
    ) -> None:
        """
        :param chat_replies: The profile's setting. `False` turns replying off for
            the session: nothing is checked at start, and only the alarm runs.
        :param model_factory: Makes the model; `AnthropicModel` by default.
        :param clock: Seconds, for the read delay, the limits and the
            conversation.
        :param sleep: Waits out what is left of the read delay.
        :param rng: Where the read delays' jitter is drawn.
        :raises StartupRefused: Replying is on, and the instructions don't load
            or the model can't be reached.
        """
        super().__init__(metadata, data, pipe)
        self._discord_config = discord_config
        self._last_status: Status | None = None
        if not self.data.has_chat_attributes:
            self._create_chat_attributes()
        ign = self.data.ign
        self._clock = clock
        self._sleep = sleep
        self._rng = rng or random.Random()
        self._conversation = Conversation(ign, clock=clock)
        self._addressing = Addressing(ign)
        self._relay: Relay | None = None
        self._calls: _CallLimit | None = None
        if chat_replies:
            self._relay, self._calls = self._start_replies(
                model_factory or AnthropicModel
            )
        self._discord = discord_config.is_file()
        self._mention = discord_mention() if self._discord else None
        # Filled in Main Process by the reply's callback, once it is typed.
        self._typed = self._proxies.instance(f"{self} - typed", "Queue")

        self._first_read = True
        self._held: list[_Read] = []
        self._replying: asyncio.Task | None = None
        self._typing_since: float | None = None
        self._appeared: dict[int, float] = {}
        self._jitter: dict[int, float] = {}
        self._announced: set[int] = set()
        self._exchanged: list[tuple[str | None, float]] = []
        self._stopped: tuple[str, ...] = ()
        self._limited = False

    # --- startup ---------------------------------------------------------------

    def _start_replies(
        self, factory: Callable[[], CheckedModel]
    ) -> tuple[Relay, _CallLimit]:
        ign = self.data.ign
        try:
            instructions = load_instructions(ign)
        except InstructionsError as exc:
            self._refuse(f"the chat replies' instructions don't load: {exc}")
        cause = _check(factory())
        if cause is not None:
            self._refuse(f"{DEFAULT_MODEL_ID} can't be reached: {cause}")
        calls = _CallLimit(factory(), self._clock)
        return Relay(calls, instructions, ign), calls

    def _refuse(self, cause: str) -> NoReturn:
        message = (
            f"Refusing to start {self.data.ign}: {cause}. Fix it, or set "
            "`chat_replies: false` in the profile's settings to run without "
            "replies (the GM alarm still runs)."
        )
        logger.critical(message)
        raise StartupRefused(message)

    # --- the loop --------------------------------------------------------------

    async def task(self) -> None:
        try:
            await super().task()
        finally:
            if self._replying is not None:
                self._replying.cancel()

    async def _decide(self) -> None:
        self._take_typed()
        self.data.update_attributes("current_frame", "chat_lines")
        reading: Reading[list[ChatLine]] = self.data.chat_lines
        self._log_status(reading)
        if reading.value is not None:
            now = self._clock()
            for line in reading.value:
                self._read(line, now, earlier=self._first_read)
            self._first_read = False
        self._follow()
        self._collect()
        self._maybe_reply()

    def _log_status(self, reading: Reading[list[ChatLine]]) -> None:
        """Log an unreadable chat once per change of status, not every cycle."""
        if reading.status is self._last_status:
            return
        self._last_status = reading.status
        if reading.status is not Status.READ:
            logger.info(
                "%s can't read the chat: %s (%s)",
                self.data.ign,
                reading.status.value,
                reading.detail,
            )

    def _read(self, line: ChatLine, now: float, *, earlier: bool) -> None:
        """One line read: the alarm first, then it waits to be appended."""
        if line.kind is ChatKind.GM:
            self._alarm(line)
        address = self._addressing.classify(line)
        if address is Address.GM:
            self._stop_training()
        self._held.append(_Read(line, address, now, earlier))

    def _follow(self) -> None:
        """Append the lines read, unless a reply is being typed: they wait for
        its echo to be registered."""
        if self._typing_since is not None:
            if self._clock() - self._typing_since < ECHO_WAIT:
                return
            logger.warning(
                "%s: no word that the reply was typed after %.0f s; following "
                "the chat again.",
                self.data.ign,
                ECHO_WAIT,
            )
            self._typing_since = None
        touched: dict[int, Entry] = {}
        for read in self._held:
            entry = self._conversation.append(
                read.line,
                read.address,
                replies_on=self._answering() and not read.earlier,
            )
            if entry is None:
                continue
            self._appeared.setdefault(entry.seq, read.at)
            if not read.earlier:
                touched[entry.seq] = entry
        self._held.clear()
        # After the whole read, so a wrapped line is announced once, joined.
        for entry in touched.values():
            self._announce(entry)

    def _announce(self, entry: Entry) -> None:
        """`chat.line_addressed`, once per line, the first time it is addressed;
        and, with replies off, the line on Discord."""
        if (
            entry.seq in self._announced
            or entry.ours
            or entry.address is Address.IGNORE
        ):
            return
        self._announced.add(entry.seq)
        payload: LineAddressedPayload = {
            "seq": entry.seq,
            "kind": entry.kind.value,
            "address": entry.address.value,
        }
        self.emit(CHAT_LINE_ADDRESSED, payload)
        if entry.state is EntryState.CONTEXT and self._relay is not None:
            logger.info("%s, replies off: %s", self.data.ign, _said(entry))
            if self._discord:
                mirror_unanswered(self.pipe.send, entry, self._mention)

    def _answering(self) -> bool:
        """Whether automatic replies are on: in the profile, from Discord, and
        not past the session's limit."""
        return self._relay is not None and not self._limited and self.data.replies_on

    # --- replying --------------------------------------------------------------

    def _take_typed(self) -> None:
        """Register the echo of each reply Main Process says it typed."""
        while True:
            try:
                text, channel = self._typed.get_nowait()
            except queue.Empty:
                return
            self._conversation.expect_echo(text, ChatKind(channel))
            self._typing_since = None

    def _collect(self) -> None:
        """Forget a reply that ended; one that raised raises here."""
        task = self._replying
        if task is None or not task.done():
            return
        self._replying = None
        if not task.cancelled() and (error := task.exception()) is not None:
            raise error

    def _maybe_reply(self) -> None:
        """Start a reply to the first burst that may have one, if none is in
        flight."""
        if (
            self._relay is None
            or self._limited
            or self._replying is not None
            or self._typing_since is not None
        ):
            return
        if not self.data.replies_on:
            self._give_up_pending()
            return
        now = self._clock()
        bursts = sorted(
            self._conversation.pending(), key=lambda b: -STRENGTH[b.address]
        )
        for burst in bursts:
            if self._exchanged_lately(burst.speaker, now):
                continue
            refusal = _refusal(burst)
            if refusal is not None:
                self._resolve(burst, refusal, self.correlation_id)
                continue
            self._replying = asyncio.create_task(
                self._reply(burst, self.correlation_id), name=f"{self} - reply"
            )
            return

    def _give_up_pending(self) -> None:
        """Replies were turned off: what was left to answer never will be."""
        for burst in self._conversation.pending():
            self._resolve(
                burst,
                Failed("replies were turned off", "replies_off"),
                self.correlation_id,
            )

    async def _reply(self, burst: Burst, correlation_id: str | None) -> None:
        """Ask for a reply to `burst`, wait out the read delay, and send it."""
        assert self._relay is not None
        assert self._calls is not None
        asked = self._clock()
        outcome = await self._relay.reply(
            self._conversation,
            list(burst.entries),
            burst.address,
            correlation_id=correlation_id,
        )
        model_s = self._clock() - asked
        if self._calls.exceeded:
            self._end_session(correlation_id)
            return
        if not isinstance(outcome, Reply):
            self._exchanged.append((burst.speaker, self._clock()))
            self._resolve(burst, outcome, correlation_id)
            return
        wait = max(0.0, self._ready_at(burst) - self._clock())
        await self._sleep(wait)
        self._exchanged.append((burst.speaker, self._clock()))
        if not self._answering():
            self._resolve(
                burst,
                Failed("replies were turned off before it was sent", "replies_off"),
                correlation_id,
            )
            return
        self._send(burst, outcome.text, model_s, wait, correlation_id)

    def _ready_at(self, burst: Burst) -> float:
        """When every line of `burst` has been read: each one's read delay after
        it appeared."""
        return max(
            self._appeared[e.seq]
            + read_delay(
                len(e.message or ""),
                self._jitter.setdefault(
                    e.seq, self._rng.uniform(1 - READ_JITTER, 1 + READ_JITTER)
                ),
            )
            for e in burst.entries
        )

    def _send(
        self,
        burst: Burst,
        text: str,
        model_s: float,
        wait_s: float,
        correlation_id: str | None,
    ) -> None:
        channel = CHANNELS[burst.channel]
        ign = self.data.ign
        self.send(
            ActionRequest(
                f"{self} - reply",
                reply_in_chat,
                ign,
                priorities.ANTI_DETECTION,
                block_lower_priority=True,
                cancel_tasks=[f"{name}({ign})" for name in TRAINING_ACTIONS],
                args=(
                    self.data.handle,
                    text,
                    channel,
                    burst.speaker if channel == "whisper" else None,
                    TypingPace(),
                ),
                kwargs={"keys": self.data.chat_keys},
                callbacks=[partial(self._typed.put_nowait, (text, channel))],
            ),
            correlation_id,
        )
        self._typing_since = self._clock()
        self._conversation.resolve(burst, EntryState.ANSWERED)
        sent: ReplySentPayload = {
            "seq": burst.entries[-1].seq,
            "channel": channel,
            "chars": len(text),
            "model_ms": round(model_s * 1000),
            "wait_ms": round(wait_s * 1000),
        }
        self.emit(CHAT_REPLY_SENT, sent, correlation_id)
        logger.info("%s replies: %s -> %s", ign, _said(*burst.entries), text)
        self._mirror(burst, Reply(text))

    def _resolve(
        self, burst: Burst, outcome: Silent | Failed, correlation_id: str | None
    ) -> None:
        """`burst` gets no reply: say so, in telemetry, the log and Discord."""
        seq = burst.entries[-1].seq
        if isinstance(outcome, Silent):
            self._conversation.resolve(burst, EntryState.SILENT)
            silent: ReplySilentPayload = {"seq": seq, "address": burst.address.value}
            self.emit(CHAT_REPLY_SILENT, silent, correlation_id)
            logger.info("%s stays silent: %s", self.data.ign, _said(*burst.entries))
        else:
            self._conversation.resolve(burst, EntryState.FAILED)
            failed: ReplyFailedPayload = {"seq": seq, "reason": outcome.cause}
            self.emit(CHAT_REPLY_FAILED, failed, correlation_id)
            logger.warning(
                "%s doesn't reply (%s): %s",
                self.data.ign,
                outcome.reason,
                _said(*burst.entries),
            )
        self._mirror(burst, outcome)

    def _mirror(self, burst: Burst, outcome: RelayOutcome) -> None:
        if self._discord:
            mirror(self.pipe.send, burst, outcome, self._mention)

    def _exchanged_lately(self, speaker: str | None, now: float) -> bool:
        self._exchanged = [
            (s, t) for s, t in self._exchanged if now - t < PLAYER_INTERVAL
        ]
        return any(same_speaker(s, speaker) for s, _ in self._exchanged)

    # --- the session's limit ---------------------------------------------------

    def _end_session(self, correlation_id: str | None) -> None:
        """Past the session's model calls: close the game and end the session."""
        assert self._calls is not None
        self._limited = True
        calls = self._calls.in_window()
        message = (
            f"{self.data.ign}: {calls} chat reply model calls in "
            f"{SESSION_WINDOW / 60:.0f} minutes, the session's limit. Closing "
            "the game and ending the session."
        )
        logger.critical(message)
        limited: ReplyLimitedPayload = {"calls_in_window": calls}
        self.emit(CHAT_REPLY_LIMITED, limited, correlation_id)
        ign = self.data.ign
        self.send(
            ActionRequest(
                f"{self} - limit reached",
                close_the_game,
                ign,
                priorities.KILL_SWITCH,
                block_lower_priority=True,
                cancel_tasks=[f"{name}({ign})" for name in TRAINING_ACTIONS],
                args=(self.data.handle,),
                discord_request=(
                    DiscordRequest(
                        f"{self._mention} {message}" if self._mention else message
                    )
                    if self._discord
                    else None
                ),
            ),
            correlation_id,
        )

    # --- a GM --------------------------------------------------------------------

    def _alarm(self, line: ChatLine) -> None:
        logger.critical("%s sees a GM line in the chat: %r", self.data.ign, line.text)
        payload: ChatLinePayload = {
            "kind": line.kind.value,
            "text": line.text,
            "row_top": int(line.top),
        }
        self.emit(CHAT_GM_LINE, payload)
        if self._discord:
            message = f"{self.data.ign}: a GM line in the chat" + (
                f": {line.text}" if line.text is not None else ""
            )
            self.send(
                ActionRequest(
                    f"{self} - GM alert",
                    _noop,
                    ign=self.data.ign,
                    priority=priorities.ANTI_DETECTION,
                    cancels_itself=True,
                    discord_request=DiscordRequest(message, line.image),
                )
            )

    def _stop_training(self) -> None:
        """A GM is talking: disable every other DecisionMaker of the bot, until
        RESUME."""
        if self._stopped:
            return
        mine = type(self).__name__
        names = tuple(n for n in self.data.decision_maker_names if n != mine)
        if not names:
            return
        logger.critical(
            "%s: a GM is talking. Training stops until RESUME: %s.",
            self.data.ign,
            ", ".join(names),
        )
        self._disable_decision_makers(*names)
        self._stopped = names

    def on_resume(self) -> tuple[str, ...]:
        """RESUME gives back what a GM stopped, and nothing else."""
        stopped, self._stopped = self._stopped, ()
        if stopped:
            logger.info(
                "%s: RESUME, training is given back: %s.",
                self.data.ign,
                ", ".join(stopped),
            )
            self._enable_decision_makers(*stopped)
        return stopped


def _refusal(burst: Burst) -> Failed | None:
    """Why `burst` gets no reply without asking the model, if it doesn't."""
    if not any(e.message for e in burst.entries):
        return Failed("nothing of what was said was read", "nothing_read")
    if CHANNELS[burst.channel] == "whisper" and (
        burst.speaker is None or UNREAD in burst.speaker
    ):
        return Failed(
            "the whisper's sender wasn't read in full: no one to whisper to",
            "no_target",
        )
    return None


def _said(*entries: Entry) -> str:
    """What `entries` said, for the log."""
    first = entries[0]
    said = " / ".join(e.message or "?" for e in entries)
    return f"[{first.kind.value}] {first.speaker or '?'}: {said}"


def _check(model: CheckedModel) -> str | None:
    """
    `model.check()`, from a thread with its own event loop: a DecisionMaker is
    built inside the Engine's running loop, which `asyncio.run` can't nest in.
    The model is used for this check only, so the session's model never holds a
    connection made on another loop.
    """
    with concurrent.futures.ThreadPoolExecutor(1) as pool:
        return pool.submit(asyncio.run, model.check()).result()


async def close_the_game(handle: int) -> None:
    """
    In Main Process: release every key, close the game, and end the session as
    `KILL` does. The session ends even when the game won't close.
    """
    controller.release_all(handle)
    try:
        close_client(handle)
    except ClientNotClosed:
        logger.critical("The game could not be closed.", exc_info=True)
    raise KeyboardInterrupt("Chat replies passed the session's model call limit.")


async def _noop() -> None:
    """An Action whose whole purpose is the Discord alert riding on it."""
