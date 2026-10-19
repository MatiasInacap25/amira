"""Chat real-time stream: broker fan-out, the SSE endpoint, and the pg_notify listener handler."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from amira_api.auth import AuthenticatedUser, get_verified_user
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.realtime import (
    STREAM_CLOSED,
    ChatBroker,
    TooManyStreams,
    handle_notify,
    listener_database_url,
    parse_chat_event,
    start_chat_listener,
)
from amira_api.realtime_routes import StreamTiming, get_chat_broker, get_clock, get_stream_timing
from amira_api.settings import Settings, get_settings

ALICE = UUID("5f0c1e2a-0000-4000-8000-00000000000a")
BOB = UUID("5f0c1e2a-0000-4000-8000-00000000000b")
CHAT = UUID("5f0c1e2a-0000-4000-8000-0000000000c1")
MESSAGE = UUID("5f0c1e2a-0000-4000-8000-0000000000d1")
BOB_MESSAGE = UUID("5f0c1e2a-0000-4000-8000-0000000000d2")
QUOTATION = UUID("5f0c1e2a-0000-4000-8000-0000000000e1")
T0 = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def message_payload(message_id: UUID, recipients: list[UUID], actor_id: UUID = ALICE) -> dict:
    return {
        "kind": "message.created",
        "chatId": str(CHAT),
        "messageId": str(message_id),
        "actorId": str(actor_id),
        "recipients": [str(user_id) for user_id in recipients],
    }


def quotation_payload(recipients: list[UUID], actor_id: UUID = ALICE) -> dict:
    return {
        "kind": "quotation.changed",
        "chatId": str(CHAT),
        "quotationId": str(QUOTATION),
        "actorId": str(actor_id),
        "recipients": [str(user_id) for user_id in recipients],
    }


class FakeClock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


async def wait_for_subscriber(broker: ChatBroker, user_id: UUID) -> None:
    while broker.subscriber_count(user_id) == 0:
        await asyncio.sleep(0.001)


async def nothing() -> None:
    return None


def user_for(auth_id: UUID, expires_at: datetime | None) -> AuthenticatedUser:
    return AuthenticatedUser(
        id=auth_id,
        email="caller@example.test",
        session_id=uuid4(),
        assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
        expires_at=expires_at,
    )


class RecordingSession:
    def __init__(self):
        self.closed = False


def recording_session_dependency(sessions: list[RecordingSession]) -> Callable[[], Iterator[RecordingSession]]:
    def dependency() -> Iterator[RecordingSession]:
        session = RecordingSession()
        sessions.append(session)
        try:
            yield session
        finally:
            session.closed = True

    return dependency


def open_stream(auth_id: UUID, expires_at: datetime | None, during: Callable[[], Awaitable[None]]) -> httpx.Response:
    """GET /api/chats/events as auth_id while `during` publishes and moves the clock."""

    async def run() -> httpx.Response:
        app.dependency_overrides[get_verified_user] = lambda: user_for(auth_id, expires_at)
        app.dependency_overrides.setdefault(get_db_session, lambda: None)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            worker = asyncio.create_task(during())
            response = await asyncio.wait_for(client.get("/api/chats/events"), timeout=5)
            await worker
            return response

    return asyncio.run(run())


@pytest.fixture
def stream():
    broker = ChatBroker()
    clock = FakeClock(T0)
    app.dependency_overrides[get_chat_broker] = lambda: broker
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_stream_timing] = lambda: StreamTiming(keepalive_seconds=0.01)
    yield broker, clock
    for dependency in (get_chat_broker, get_clock, get_stream_timing, get_verified_user, get_db_session):
        app.dependency_overrides.pop(dependency, None)


# Broker: in-process fan-out.


def test_publish_delivers_only_to_listed_recipients():
    broker = ChatBroker()
    alice = broker.subscribe(ALICE)
    bob = broker.subscribe(BOB)
    payload = message_payload(MESSAGE, [ALICE])

    broker.publish(payload)

    assert alice.queue.get_nowait() == payload
    assert bob.queue.empty()


def test_broker_keeps_the_payload_intact_and_leaves_stripping_to_the_endpoint():
    broker = ChatBroker()
    alice = broker.subscribe(ALICE)
    payload = quotation_payload([ALICE, BOB])

    broker.publish(payload)

    assert alice.queue.get_nowait() == payload


def test_sixth_open_stream_for_one_user_is_refused_until_a_slot_is_released():
    broker = ChatBroker(max_streams_per_user=5)
    streams = [broker.subscribe(ALICE) for _ in range(5)]

    with pytest.raises(TooManyStreams):
        broker.subscribe(ALICE)
    assert broker.subscribe(BOB) is not None

    broker.unsubscribe(streams[0])
    assert broker.subscribe(ALICE) is not None


def test_slow_subscriber_is_dropped_without_blocking_the_others():
    broker = ChatBroker(queue_size=1)
    slow = broker.subscribe(ALICE)
    fast = broker.subscribe(ALICE)
    first = message_payload(MESSAGE, [ALICE])
    second = message_payload(BOB_MESSAGE, [ALICE])

    broker.publish(first)
    assert fast.queue.get_nowait() == first

    broker.publish(second)

    assert slow.closed is True
    assert slow.queue.get_nowait() is STREAM_CLOSED
    assert fast.queue.get_nowait() == second
    assert broker.subscriber_count(ALICE) == 1


# Listener handler: parse notify payloads and publish the valid ones.


def test_full_queue_closes_the_stream_on_a_state_change():
    broker = ChatBroker(queue_size=1)
    subscription = broker.subscribe(ALICE)
    broker.publish(message_payload(MESSAGE, [ALICE]))

    broker.set_listening(True)

    assert subscription.closed is True
    assert subscription.queue.get_nowait() is STREAM_CLOSED
    assert broker.subscriber_count(ALICE) == 0


def test_parse_accepts_message_and_quotation_payloads():
    assert parse_chat_event(json.dumps(message_payload(MESSAGE, [ALICE, BOB]))) == message_payload(MESSAGE, [ALICE, BOB])
    assert parse_chat_event(json.dumps(quotation_payload([BOB]))) == quotation_payload([BOB])


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        json.dumps({**message_payload(MESSAGE, [ALICE]), "kind": "unknown.kind"}),
        json.dumps({k: v for k, v in message_payload(MESSAGE, [ALICE]).items() if k != "messageId"}),
        json.dumps({k: v for k, v in quotation_payload([ALICE]).items() if k != "quotationId"}),
        json.dumps({**message_payload(MESSAGE, [ALICE]), "chatId": "not-a-uuid"}),
        json.dumps({k: v for k, v in message_payload(MESSAGE, [ALICE]).items() if k != "actorId"}),
        json.dumps({**message_payload(MESSAGE, [ALICE]), "actorId": "not-a-uuid"}),
        json.dumps({**message_payload(MESSAGE, [ALICE]), "recipients": []}),
        json.dumps({**message_payload(MESSAGE, [ALICE]), "recipients": "alice"}),
        json.dumps({**message_payload(MESSAGE, [ALICE]), "recipients": ["nope"]}),
    ],
)
def test_parse_ignores_malformed_payloads(raw):
    assert parse_chat_event(raw) is None


def test_handler_publishes_valid_payloads_and_ignores_malformed_ones():
    broker = ChatBroker()
    alice = broker.subscribe(ALICE)
    payload = message_payload(MESSAGE, [ALICE])

    handle_notify("garbage", broker)
    handle_notify(json.dumps(payload), broker)

    assert alice.queue.get_nowait() == payload
    assert alice.queue.empty()


def test_listener_prefers_realtime_url_and_falls_back_to_database_url():
    both = Settings(
        realtime_database_url="postgresql+psycopg://u:p@session.example.test:5432/amira",
        database_url="postgresql+psycopg://u:p@pooler.example.test:6543/amira",
    )
    only_database = Settings(database_url="postgresql+psycopg://u:p@pooler.example.test:6543/amira")

    assert listener_database_url(both) == "postgresql://u:p@session.example.test:5432/amira"
    assert listener_database_url(only_database) == "postgresql://u:p@pooler.example.test:6543/amira"
    assert listener_database_url(Settings()) is None


def test_listener_does_not_start_without_a_database_url():
    assert start_chat_listener(ChatBroker(), Settings()) is None


# Endpoint.


def test_stream_requires_a_bearer_token_and_ignores_tokens_in_the_url():
    app.dependency_overrides[get_settings] = lambda: Settings(supabase_jwt_issuer="https://auth.example.test/auth/v1")
    app.dependency_overrides[get_db_session] = lambda: None
    try:
        client = TestClient(app)

        assert client.get("/api/chats/events").status_code == 401
        assert client.get("/api/chats/events?access_token=abc").status_code == 401
    finally:
        app.dependency_overrides.pop(get_settings, None)
        app.dependency_overrides.pop(get_db_session, None)


def test_stream_without_token_expiry_is_refused(stream):
    response = open_stream(ALICE, expires_at=None, during=nothing)

    assert response.status_code == 401


def test_stream_sends_only_the_callers_events_without_recipients(stream):
    broker, clock = stream
    expires_at = T0 + timedelta(minutes=1)

    async def during() -> None:
        await wait_for_subscriber(broker, ALICE)
        broker.publish(message_payload(BOB_MESSAGE, [BOB], actor_id=BOB))
        broker.publish(message_payload(MESSAGE, [ALICE]))
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(ALICE, expires_at=expires_at, during=during)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    frames = [block for block in response.text.split("\n\n") if block.startswith("event:")]
    assert len(frames) == 1
    name, data = frames[0].split("\n")
    assert name == "event: message.created"
    assert json.loads(data.removeprefix("data: ")) == {
        "kind": "message.created",
        "chatId": str(CHAT),
        "messageId": str(MESSAGE),
        "fromMe": True,
    }
    assert str(BOB_MESSAGE) not in response.text


def test_stream_marks_the_actors_own_event_fromMe_true_and_hides_actor_and_recipients(stream):
    broker, clock = stream

    async def during() -> None:
        await wait_for_subscriber(broker, ALICE)
        broker.publish(message_payload(MESSAGE, [ALICE, BOB], actor_id=ALICE))
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(ALICE, expires_at=T0 + timedelta(minutes=1), during=during)

    assert json.loads(response.text.split("data: ", 1)[1].split("\n", 1)[0])["fromMe"] is True
    assert "actorId" not in response.text
    assert "recipients" not in response.text


def test_stream_marks_the_other_participants_event_fromMe_false_and_hides_actor_and_recipients(stream):
    broker, clock = stream

    async def during() -> None:
        await wait_for_subscriber(broker, BOB)
        broker.publish(message_payload(MESSAGE, [ALICE, BOB], actor_id=ALICE))
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(BOB, expires_at=T0 + timedelta(minutes=1), during=during)

    assert json.loads(response.text.split("data: ", 1)[1].split("\n", 1)[0])["fromMe"] is False
    assert "actorId" not in response.text
    assert "recipients" not in response.text


def test_stream_emits_keepalive_comments_while_idle(stream):
    broker, clock = stream

    async def during() -> None:
        await wait_for_subscriber(broker, ALICE)
        await asyncio.sleep(0.05)
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(ALICE, expires_at=T0 + timedelta(minutes=1), during=during)

    assert ": keepalive\n\n" in response.text


def test_stream_closes_at_token_expiry_and_releases_its_slot(stream):
    broker, clock = stream

    async def during() -> None:
        await wait_for_subscriber(broker, ALICE)
        clock.now = T0 + timedelta(minutes=2)

    response = open_stream(ALICE, expires_at=T0 + timedelta(minutes=1), during=during)

    assert response.status_code == 200
    assert broker.subscriber_count(ALICE) == 0


def test_sixth_stream_for_one_user_gets_429(stream):
    broker, _clock = stream
    for _ in range(5):
        broker.subscribe(ALICE)

    response = open_stream(ALICE, expires_at=T0 + timedelta(hours=1), during=nothing)

    assert response.status_code == 429


# Listener state: streams announce ready and degraded.


def test_listener_state_changes_are_pushed_only_when_they_change():
    broker = ChatBroker()
    alice = broker.subscribe(ALICE)

    broker.set_listening(False)
    assert alice.queue.empty()

    broker.set_listening(True)
    broker.set_listening(True)
    assert alice.queue.get_nowait() == "ready"
    assert alice.queue.empty()


def test_stream_without_a_listening_listener_sends_no_ready(stream):
    _broker, clock = stream

    async def during() -> None:
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(ALICE, expires_at=T0 + timedelta(minutes=1), during=during)

    assert "event: ready" not in response.text


def test_stream_sends_ready_when_the_listener_is_listening(stream):
    broker, clock = stream
    broker.set_listening(True)

    async def during() -> None:
        await wait_for_subscriber(broker, ALICE)
        await asyncio.sleep(0.05)
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(ALICE, expires_at=T0 + timedelta(minutes=1), during=during)

    assert "event: ready\ndata: {}\n\n" in response.text


def test_listener_state_change_pushes_degraded_then_ready_to_open_streams(stream):
    broker, clock = stream

    async def during() -> None:
        await wait_for_subscriber(broker, ALICE)
        broker.set_listening(True)
        broker.set_listening(False)
        broker.set_listening(True)
        await asyncio.sleep(0.05)
        clock.now = T0 + timedelta(hours=1)

    response = open_stream(ALICE, expires_at=T0 + timedelta(minutes=1), during=during)

    states = [
        block.split("\n")[0]
        for block in response.text.split("\n\n")
        if block.startswith(("event: ready", "event: degraded"))
    ]
    assert states[-2:] == ["event: degraded", "event: ready"]


def test_keepalive_defaults_to_twenty_seconds():
    assert StreamTiming().keepalive_seconds == 20


def test_auth_session_is_closed_before_the_first_stream_frame(stream):
    broker, clock = stream
    sessions: list[RecordingSession] = []
    app.dependency_overrides[get_db_session] = recording_session_dependency(sessions)
    app.dependency_overrides[get_verified_user] = lambda: user_for(ALICE, T0 + timedelta(hours=1))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/api/chats/events",
        "raw_path": b"/api/chats/events",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("test", 1),
        "server": ("test", 80),
    }

    async def run() -> dict:
        observed: dict = {}
        first_frame_sent = asyncio.Event()

        async def send(message: dict) -> None:
            body = message.get("body", b"")
            if message["type"] == "http.response.body" and b"event:" in body and not first_frame_sent.is_set():
                observed["closed_at_first_frame"] = sessions[0].closed
                observed["frame"] = body
                first_frame_sent.set()

        async def receive() -> dict:
            await asyncio.Event().wait()
            return {"type": "http.disconnect"}

        task = asyncio.create_task(app(scope, receive, send))
        await wait_for_subscriber(broker, ALICE)
        broker.publish(message_payload(MESSAGE, [ALICE]))
        await asyncio.wait_for(first_frame_sent.wait(), timeout=5)
        clock.now = T0 + timedelta(hours=2)
        await asyncio.wait_for(task, timeout=5)
        return observed

    observed = asyncio.run(run())

    assert observed["frame"].startswith(b"event: message.created")
    assert observed["closed_at_first_frame"] is True
