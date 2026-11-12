"""Deterministic realtime and lifespan boundaries without sockets or timed sleeps."""

import asyncio
from contextlib import nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import pytest

from amira_api import main, realtime, realtime_routes
from amira_api.settings import Settings
from test_realtime_stream import user_for


def test_chat_event_payload_enforces_notify_byte_limit():
    identifier = uuid4()
    event = realtime.ChatEvent(realtime.ChatEventKind.MESSAGE_CREATED, identifier, identifier, identifier, (identifier,) * 300)
    with pytest.raises(ValueError, match="size limit"):
        event.to_payload()


def test_broker_repeated_unsubscribe_and_closed_subscription_are_harmless():
    broker = realtime.ChatBroker()
    subscription = broker.subscribe(uuid4())
    subscription.closed = True
    broker.set_listening(True)
    assert subscription.queue.empty()
    broker.unsubscribe(subscription)
    broker.unsubscribe(subscription)
    assert broker.subscriber_count(subscription.user_id) == 0


def test_invalid_listener_url_logs_no_credentials(caplog):
    assert realtime.listener_database_url(Settings(realtime_database_url="invalid-secret")) is None
    assert "could not be parsed" in caplog.text
    assert "invalid-secret" not in caplog.text


def test_app_heartbeat_uses_transactional_engine(monkeypatch):
    connection = Mock()
    engine = Mock()
    engine.begin.return_value = nullcontext(connection)
    monkeypatch.setattr(realtime, "get_engine", lambda: engine)
    realtime.send_app_heartbeat("nonce")
    assert connection.execute.call_args.args[1] == {"channel": realtime.CHAT_HEALTH_CHANNEL, "nonce": "nonce"}


@pytest.mark.parametrize("listener", [False, True])
def test_lifespan_starts_listener_and_cancels_it_on_exit(monkeypatch, listener):
    async def run():
        started = asyncio.Event()
        cancelled = []
        async def wait():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(True)
        task = asyncio.create_task(wait()) if listener else None
        if task:
            await started.wait()
        monkeypatch.setattr(main, "start_chat_listener", lambda broker, settings: task)
        async with main.lifespan(main.app):
            assert task is None or not task.done()
        assert task is None or task.cancelled()
        assert bool(cancelled) is listener
    asyncio.run(run())


def test_stream_dependency_defaults_and_missing_expiry():
    assert realtime_routes.get_chat_broker() is realtime.chat_broker
    assert callable(realtime_routes.get_clock())
    assert realtime_routes.get_stream_timing().keepalive_seconds == 20.0
    async def run():
        from fastapi import HTTPException
        broker = realtime.ChatBroker()
        identity = user_for(uuid4(), None)
        with pytest.raises(HTTPException) as caught:
            await realtime_routes.stream_chat_events(identity, Settings(), object(), broker,
                lambda: datetime(2026, 11, 7, tzinfo=timezone.utc), realtime_routes.StreamTiming(), None)
        assert caught.value.status_code == 401 and broker.subscriber_count(identity.id) == 0
    asyncio.run(run())


def test_listener_receives_event_and_retries_after_connection_failure(monkeypatch, caplog):
    async def run():
        broker = realtime.ChatBroker()
        handled = Mock()
        monkeypatch.setattr(realtime, "handle_notify", handled)
        class Connection:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): return False
            async def execute(self, statement): pass
            async def notifies(self):
                yield NS(channel=realtime.CHAT_HEALTH_CHANNEL, payload="unknown-nonce")
                yield NS(channel=realtime.CHAT_EVENTS_CHANNEL, payload="event")
                raise OSError("secret credentials")
        async def connect(url, **options):
            assert options == {"autocommit": True, "sslmode": "require"}
            return Connection()
        async def stop(delay):
            assert delay == 0.5
            raise asyncio.CancelledError
        monkeypatch.setattr(realtime.asyncio, "sleep", stop)
        with pytest.raises(asyncio.CancelledError):
            await realtime.run_chat_listener(broker, "postgresql://db/test", connect=connect, base_delay=0.5)
        handled.assert_called_once_with("event", broker)
        assert not broker.listening
    asyncio.run(run())
    assert "retrying" in caplog.text and "secret credentials" not in caplog.text


def test_start_listener_creates_task_without_opening_connection(monkeypatch):
    async def run():
        recorded = []
        def create(coroutine):
            recorded.append(coroutine)
            coroutine.close()
            return "task"
        monkeypatch.setattr(realtime.asyncio, "create_task", create)
        assert realtime.start_chat_listener(realtime.ChatBroker(), Settings(database_url="postgresql://db/test")) == "task"
        assert len(recorded) == 1
    asyncio.run(run())


def test_stream_timeout_at_expiry_closes_without_keepalive(monkeypatch):
    from datetime import timedelta
    async def run():
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)
        expires = now + timedelta(seconds=1)
        ticks = iter([now, expires, expires])
        async def timeout(awaitable, timeout):
            awaitable.close()
            raise TimeoutError
        monkeypatch.setattr(realtime_routes.asyncio, "wait_for", timeout)
        broker = realtime.ChatBroker()
        identity = user_for(uuid4(), expires)
        response = await realtime_routes.stream_chat_events(identity, Settings(), object(), broker,
            lambda: next(ticks), realtime_routes.StreamTiming(), None)
        with pytest.raises(StopAsyncIteration):
            await anext(response.body_iterator)
        assert broker.subscriber_count(identity.id) == 0
    asyncio.run(run())


def test_dropped_stream_exits_on_closed_sentinel():
    from datetime import timedelta
    async def run():
        now = datetime(2026, 11, 7, tzinfo=timezone.utc)
        broker = realtime.ChatBroker(queue_size=1)
        identity = user_for(uuid4(), now + timedelta(minutes=1))
        response = await realtime_routes.stream_chat_events(identity, Settings(), object(), broker,
            lambda: now, realtime_routes.StreamTiming(), None)
        broker.set_listening(True)
        broker.set_listening(False)  # Queue overflow replaces pending frames with STREAM_CLOSED.
        with pytest.raises(StopAsyncIteration):
            await anext(response.body_iterator)
        assert broker.subscriber_count(identity.id) == 0
    asyncio.run(run())
