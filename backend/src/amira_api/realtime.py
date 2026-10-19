"""Chat change announcements over PostgreSQL LISTEN/NOTIFY.

Writers call publish_chat_event on the same session as their row change, before the commit. pg_notify is delivered
only when that transaction commits, so a rolled-back write announces nothing. Payloads carry ids and recipient user
ids only, never message content.

The listener task relays those notifications to the in-process ChatBroker, which fans them out to the open
per-user event streams in realtime_routes.
"""

import asyncio
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
import json
import logging
import secrets
import time
from uuid import UUID

from psycopg import AsyncConnection, sql
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.orm import Session

from amira_api.db import get_engine
from amira_api.models import ChatParticipante
from amira_api.settings import Settings

logger = logging.getLogger(__name__)

CHAT_EVENTS_CHANNEL = "amira_chat_events"
# Heartbeats travel the same NOTIFY path as chat events, so a round trip proves delivery works.
CHAT_HEALTH_CHANNEL = "amira_chat_health"
HEARTBEAT_SECONDS = 15.0
# About two heartbeat intervals: a silent LISTEN connection is reported degraded after this.
HEARTBEAT_TIMEOUT_SECONDS = 35.0
PENDING_NONCE_LIMIT = 8
# pg_notify rejects payloads of 8000 bytes or more; the builder stays far below that.
MAX_PAYLOAD_BYTES = 8000
MAX_STREAMS_PER_USER = 5
SUBSCRIBER_QUEUE_SIZE = 64
RECONNECT_BASE_SECONDS = 1.0
RECONNECT_MAX_SECONDS = 30.0
# Placed on a subscriber's queue when the broker closes its stream.
STREAM_CLOSED = object()


class ChatEventKind(StrEnum):
    MESSAGE_CREATED = "message.created"
    QUOTATION_CHANGED = "quotation.changed"


class ListenerState(StrEnum):
    """Queued for open streams when the LISTEN connection comes up (READY) or drops (DEGRADED)."""

    READY = "ready"
    DEGRADED = "degraded"


@dataclass(frozen=True)
class ChatEvent:
    kind: ChatEventKind
    chat_id: UUID
    ref_id: UUID
    recipients: tuple[UUID, ...]

    def to_payload(self) -> str:
        ref_key = "messageId" if self.kind is ChatEventKind.MESSAGE_CREATED else "quotationId"
        payload = json.dumps(
            {
                "kind": self.kind.value,
                "chatId": str(self.chat_id),
                ref_key: str(self.ref_id),
                "recipients": [str(user_id) for user_id in self.recipients],
            },
            separators=(",", ":"),
        )
        if len(payload.encode()) >= MAX_PAYLOAD_BYTES:
            raise ValueError("Chat event payload exceeds the pg_notify size limit.")
        return payload


def publish_chat_event(session: Session, *, chat_id: UUID, kind: ChatEventKind | str, ref_id: UUID) -> None:
    """Announce a chat change to both participants, inside the caller's transaction."""
    event_kind = ChatEventKind(kind)
    recipients = tuple(
        session.execute(
            select(ChatParticipante.user_id)
            .where(ChatParticipante.chat_id == chat_id)
            .order_by(ChatParticipante.user_id)
        ).scalars()
    )
    if not recipients:
        return
    event = ChatEvent(kind=event_kind, chat_id=chat_id, ref_id=ref_id, recipients=recipients)
    session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": CHAT_EVENTS_CHANNEL, "payload": event.to_payload()},
    )


class TooManyStreams(Exception):
    """The user already holds the maximum number of open chat event streams."""


class Subscription:
    def __init__(self, user_id: UUID, queue_size: int):
        self.user_id = user_id
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        self.closed = False


class ChatBroker:
    """In-process fan-out from the listener to open streams, keyed by recipient user id."""

    def __init__(self, *, max_streams_per_user: int = MAX_STREAMS_PER_USER, queue_size: int = SUBSCRIBER_QUEUE_SIZE):
        self._max_streams_per_user = max_streams_per_user
        self._queue_size = queue_size
        self._subscribers: dict[UUID, set[Subscription]] = {}
        self._listening = False

    @property
    def listening(self) -> bool:
        return self._listening

    def set_listening(self, listening: bool) -> None:
        """Record whether the LISTEN connection is up, and tell every open stream when that changes."""
        if self._listening == listening:
            return
        self._listening = listening
        state = ListenerState.READY if listening else ListenerState.DEGRADED
        for subscribers in tuple(self._subscribers.values()):
            for subscription in tuple(subscribers):
                self._deliver(subscription, state)

    def subscriber_count(self, user_id: UUID) -> int:
        return len(self._subscribers.get(user_id, ()))

    def subscribe(self, user_id: UUID) -> Subscription:
        current = self._subscribers.setdefault(user_id, set())
        if len(current) >= self._max_streams_per_user:
            raise TooManyStreams
        subscription = Subscription(user_id, self._queue_size)
        current.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        subscribers = self._subscribers.get(subscription.user_id)
        if subscribers is None:
            return
        subscribers.discard(subscription)
        if not subscribers:
            del self._subscribers[subscription.user_id]

    def publish(self, payload: dict) -> None:
        """Deliver the payload to the open streams of its recipients only. Slow subscribers are dropped."""
        for recipient in {UUID(user_id) for user_id in payload["recipients"]}:
            for subscription in tuple(self._subscribers.get(recipient, ())):
                self._deliver(subscription, payload)

    def _deliver(self, subscription: Subscription, payload: dict | ListenerState) -> None:
        if subscription.closed:
            return
        try:
            subscription.queue.put_nowait(payload)
        except asyncio.QueueFull:
            self._drop(subscription)

    def _drop(self, subscription: Subscription) -> None:
        subscription.closed = True
        self.unsubscribe(subscription)
        while not subscription.queue.empty():
            subscription.queue.get_nowait()
        subscription.queue.put_nowait(STREAM_CLOSED)


chat_broker = ChatBroker()


def _is_uuid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
    except ValueError:
        return False
    return True


def parse_chat_event(raw: str) -> dict | None:
    """Return the notify payload rebuilt from its known fields, or None when it is not a valid chat event."""
    try:
        event = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(event, dict):
        return None
    try:
        kind = ChatEventKind(event.get("kind"))
    except ValueError:
        return None
    ref_key = "messageId" if kind is ChatEventKind.MESSAGE_CREATED else "quotationId"
    recipients = event.get("recipients")
    if not isinstance(recipients, list) or not recipients or not all(_is_uuid(user_id) for user_id in recipients):
        return None
    if not _is_uuid(event.get("chatId")) or not _is_uuid(event.get(ref_key)):
        return None
    return {"kind": kind.value, "chatId": event["chatId"], ref_key: event[ref_key], "recipients": recipients}


def handle_notify(raw: str, broker: ChatBroker) -> None:
    event = parse_chat_event(raw)
    if event is None:
        logger.warning("Ignored a malformed chat event notification.")
        return
    broker.publish(event)


class ListenerHealth:
    """Heartbeat nonces the listener sent, and when one last came back on the LISTEN connection."""

    def __init__(self, *, timeout_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._timeout_seconds = timeout_seconds
        self._clock = clock
        self._pending: deque[str] = deque(maxlen=PENDING_NONCE_LIMIT)
        self._confirmed_at: float | None = None

    def issue(self) -> str:
        nonce = secrets.token_urlsafe(16)
        self._pending.append(nonce)
        return nonce

    def confirm(self, nonce: str) -> bool:
        try:
            self._pending.remove(nonce)
        except ValueError:
            return False
        self._confirmed_at = self._clock()
        return True

    def is_fresh(self) -> bool:
        return self._confirmed_at is not None and self._clock() - self._confirmed_at <= self._timeout_seconds


def send_app_heartbeat(nonce: str) -> None:
    """Send one heartbeat through the app engine (DATABASE_URL), in a short transaction."""
    with get_engine().begin() as connection:
        connection.execute(text("SELECT pg_notify(:channel, :nonce)"), {"channel": CHAT_HEALTH_CHANNEL, "nonce": nonce})


async def _send_heartbeats(
    broker: ChatBroker,
    health: ListenerHealth,
    send_heartbeat: Callable[[str], None],
    interval_seconds: float,
) -> None:
    while True:
        nonce = health.issue()
        try:
            # The engine is synchronous; running it in a thread keeps the event loop free.
            await asyncio.to_thread(send_heartbeat, nonce)
        except Exception as exc:
            logger.warning("Chat heartbeat was not sent (%s).", type(exc).__name__)
        await asyncio.sleep(interval_seconds)
        if not health.is_fresh():
            broker.set_listening(False)


def listener_database_url(settings: Settings) -> str | None:
    """A plain postgresql:// URL for psycopg, from REALTIME_DATABASE_URL or DATABASE_URL."""
    url = settings.realtime_database_url or settings.database_url
    if not url:
        return None
    try:
        return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)
    except ArgumentError:
        # The message can echo the URL, so it is not logged.
        logger.error("The chat real-time database URL could not be parsed; the chat listener is disabled.")
        return None


async def run_chat_listener(
    broker: ChatBroker,
    database_url: str,
    *,
    base_delay: float = RECONNECT_BASE_SECONDS,
    max_delay: float = RECONNECT_MAX_SECONDS,
    connect: Callable[..., Awaitable[AsyncConnection]] = AsyncConnection.connect,
    send_heartbeat: Callable[[str], None] | None = None,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
    heartbeat_timeout_seconds: float = HEARTBEAT_TIMEOUT_SECONDS,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    delay = base_delay
    while True:
        health = ListenerHealth(timeout_seconds=heartbeat_timeout_seconds, clock=clock)
        heartbeat: asyncio.Task | None = None
        try:
            async with await connect(database_url, autocommit=True, sslmode="require") as connection:
                await connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(CHAT_EVENTS_CHANNEL)))
                await connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(CHAT_HEALTH_CHANNEL)))
                delay = base_delay
                # Ready only once a heartbeat comes back; LISTEN succeeding proves nothing about delivery.
                if send_heartbeat is None:
                    logger.warning("Chat heartbeat disabled: DATABASE_URL is not set, so live updates stay degraded.")
                else:
                    heartbeat = asyncio.create_task(_send_heartbeats(broker, health, send_heartbeat, heartbeat_seconds))
                async for notification in connection.notifies():
                    if notification.channel == CHAT_HEALTH_CHANNEL:
                        if health.confirm(notification.payload):
                            broker.set_listening(True)
                        continue
                    handle_notify(notification.payload, broker)
        except Exception as exc:
            # Only the exception type is logged: driver messages can echo connection details.
            logger.warning("Chat listener lost its connection (%s); retrying in %.0f s.", type(exc).__name__, delay)
        finally:
            if heartbeat is not None:
                heartbeat.cancel()
            broker.set_listening(False)
        await asyncio.sleep(delay)
        delay = min(delay * 2, max_delay)


def start_chat_listener(broker: ChatBroker, settings: Settings) -> asyncio.Task | None:
    database_url = listener_database_url(settings)
    if database_url is None:
        logger.info("Chat real-time listener not started: no REALTIME_DATABASE_URL or DATABASE_URL is set.")
        return None
    send_heartbeat = send_app_heartbeat if settings.database_url else None
    return asyncio.create_task(run_chat_listener(broker, database_url, send_heartbeat=send_heartbeat))
