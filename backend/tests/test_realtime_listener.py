"""Chat listener readiness: ready only after a NOTIFY heartbeat round trip, never from LISTEN alone."""

import asyncio
import threading
from collections.abc import Awaitable, Callable
from contextlib import suppress
from types import SimpleNamespace
from uuid import UUID

from amira_api.realtime import (
    CHAT_HEALTH_CHANNEL,
    PENDING_NONCE_LIMIT,
    ChatBroker,
    ListenerHealth,
    run_chat_listener,
)

ALICE = UUID("5f0c1e2a-0000-4000-8000-00000000000a")
URL = "postgresql://listener.example.test/amira"


class FakeClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


class FakeListenerConnection:
    def __init__(self):
        self.notifications: asyncio.Queue = asyncio.Queue()
        self.executed = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc_info) -> bool:
        return False

    async def execute(self, _query) -> None:
        self.executed += 1

    async def notifies(self):
        while True:
            yield await self.notifications.get()


class FakeDatabase:
    def __init__(self):
        self.connection = FakeListenerConnection()

    async def connect(self, _url: str, **_options) -> FakeListenerConnection:
        return self.connection


class RecordingSender:
    """Stands in for the app-engine heartbeat; records the nonces and the thread that sent them."""

    def __init__(self):
        self.nonces: list[str] = []
        self.threads: list[int] = []

    def __call__(self, nonce: str) -> None:
        self.nonces.append(nonce)
        self.threads.append(threading.get_ident())


async def wait_until(predicate: Callable[[], bool], timeout: float = 2.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.001)

    await asyncio.wait_for(poll(), timeout=timeout)


async def echo(db: FakeDatabase, nonce: str, channel: str = CHAT_HEALTH_CHANNEL) -> None:
    await db.connection.notifications.put(SimpleNamespace(channel=channel, payload=nonce))


def run_listener(
    scenario: Callable[[ChatBroker, FakeDatabase, RecordingSender], Awaitable[None]],
    *,
    heartbeat: bool = True,
    timeout: float = 0.05,
) -> None:
    broker = ChatBroker()
    db = FakeDatabase()
    sender = RecordingSender()

    async def main() -> None:
        listener = asyncio.create_task(
            run_chat_listener(
                broker,
                URL,
                connect=db.connect,
                send_heartbeat=sender if heartbeat else None,
                heartbeat_seconds=0.01,
                heartbeat_timeout_seconds=timeout,
                base_delay=0.01,
                max_delay=0.01,
            )
        )
        try:
            await scenario(broker, db, sender)
        finally:
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener

    asyncio.run(main())


def test_listen_success_alone_does_not_report_ready():
    async def scenario(broker, db, sender):
        await wait_until(lambda: db.connection.executed == 2 and sender.nonces)
        await asyncio.sleep(0.03)

        assert broker.listening is False

    run_listener(scenario)


def test_matching_nonce_reports_ready():
    async def scenario(broker, db, sender):
        await wait_until(lambda: sender.nonces)
        await echo(db, sender.nonces[-1])
        await wait_until(lambda: broker.listening)

    run_listener(scenario)


def test_unknown_nonce_does_not_report_ready():
    async def scenario(broker, db, sender):
        await wait_until(lambda: sender.nonces)
        await echo(db, "not-a-nonce-we-sent")
        await asyncio.sleep(0.03)

        assert broker.listening is False

    run_listener(scenario)


def test_missing_heartbeat_within_the_timeout_reports_degraded():
    async def scenario(broker, db, sender):
        await wait_until(lambda: sender.nonces)
        await echo(db, sender.nonces[-1])
        await wait_until(lambda: broker.listening)

        await wait_until(lambda: not broker.listening)

    run_listener(scenario, timeout=0.05)


def test_health_notifications_never_reach_subscribers():
    async def scenario(broker, db, sender):
        subscription = broker.subscribe(ALICE)
        await wait_until(lambda: sender.nonces)
        await echo(db, sender.nonces[-1])
        await wait_until(lambda: broker.listening)

        queued = []
        while not subscription.queue.empty():
            queued.append(subscription.queue.get_nowait())
        assert [item for item in queued if isinstance(item, dict)] == []

    run_listener(scenario)


def test_heartbeat_sender_runs_off_the_event_loop():
    async def scenario(_broker, _db, sender):
        await wait_until(lambda: sender.nonces)

        assert sender.threads[0] != threading.get_ident()

    run_listener(scenario)


def test_without_a_heartbeat_sender_the_listener_never_reports_ready():
    async def scenario(broker, db, _sender):
        await wait_until(lambda: db.connection.executed == 2)
        await asyncio.sleep(0.03)

        assert broker.listening is False

    run_listener(scenario, heartbeat=False)


def test_listener_health_confirms_only_nonces_it_issued():
    health = ListenerHealth(timeout_seconds=35, clock=FakeClock())
    nonce = health.issue()

    assert health.confirm("someone-else") is False
    assert health.confirm(nonce) is True
    assert health.confirm(nonce) is False


def test_listener_health_keeps_only_a_bounded_set_of_pending_nonces():
    health = ListenerHealth(timeout_seconds=35, clock=FakeClock())
    nonces = [health.issue() for _ in range(PENDING_NONCE_LIMIT + 1)]

    assert health.confirm(nonces[0]) is False
    assert health.confirm(nonces[-1]) is True


def test_listener_health_is_fresh_only_within_the_timeout_of_a_confirmation():
    clock = FakeClock(now=100.0)
    health = ListenerHealth(timeout_seconds=35, clock=clock)
    assert health.is_fresh() is False

    health.confirm(health.issue())
    clock.now = 135.0
    assert health.is_fresh() is True
    clock.now = 135.5
    assert health.is_fresh() is False
