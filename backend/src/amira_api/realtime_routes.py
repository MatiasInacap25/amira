"""Per-user Server-Sent Events stream of chat changes, fed by the in-process ChatBroker."""

import asyncio
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import datetime
import json
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from amira_api.auth import AuthenticatedUser, authorize_current_user, get_verified_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.realtime import STREAM_CLOSED, ChatBroker, ListenerState, Subscription, TooManyStreams, chat_broker
from amira_api.settings import Settings, get_settings

KEEPALIVE_FRAME = ": keepalive\n\n"


@dataclass(frozen=True)
class StreamTiming:
    keepalive_seconds: float = 20.0


def get_chat_broker() -> ChatBroker:
    return chat_broker


def get_clock() -> Callable[[], datetime]:
    return utc_now


def get_stream_timing() -> StreamTiming:
    return StreamTiming()


Broker = Annotated[ChatBroker, Depends(get_chat_broker)]
Clock = Annotated[Callable[[], datetime], Depends(get_clock)]
Timing = Annotated[StreamTiming, Depends(get_stream_timing)]

router = APIRouter(prefix="/api/chats", tags=["chats"])


def _event_frame(payload: dict) -> str:
    # Recipients name the other participant's id; the client only needs the event's ids.
    data = {key: value for key, value in payload.items() if key != "recipients"}
    return f"event: {data['kind']}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def _state_frame(state: ListenerState) -> str:
    return f"event: {state.value}\ndata: {{}}\n\n"


async def _frames(
    broker: ChatBroker,
    subscription: Subscription,
    *,
    expires_at: datetime,
    clock: Callable[[], datetime],
    keepalive_seconds: float,
) -> AsyncIterator[str]:
    try:
        # A stream opened while the listener is live says so; one opened while it is down stays silent until it comes up.
        if broker.listening:
            yield _state_frame(ListenerState.READY)
        while True:
            remaining = (expires_at - clock()).total_seconds()
            if remaining <= 0:
                return
            try:
                payload = await asyncio.wait_for(subscription.queue.get(), timeout=min(keepalive_seconds, remaining))
            except TimeoutError:
                if (expires_at - clock()).total_seconds() > 0:
                    yield KEEPALIVE_FRAME
                continue
            if payload is STREAM_CLOSED:
                return
            if isinstance(payload, ListenerState):
                yield _state_frame(payload)
                continue
            yield _event_frame(payload)
    finally:
        broker.unsubscribe(subscription)


@router.get("/events")
async def stream_chat_events(
    verified_user: Annotated[AuthenticatedUser, Depends(get_verified_user)],
    settings: Annotated[Settings, Depends(get_settings)],
    # scope="function" closes the session when this function returns, before the stream starts, so a
    # long-lived stream never holds a pooled connection. Other endpoints keep the request-scoped session.
    session: Annotated[Session, Depends(get_db_session, scope="function")],
    broker: Broker,
    clock: Clock,
    timing: Timing,
    fallback_proof: str | None = Header(default=None, alias="X-Amira-Email-Fallback-Proof"),
) -> StreamingResponse:
    current_user = await run_in_threadpool(authorize_current_user, verified_user, settings, session, fallback_proof)
    if current_user.expires_at is None:
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.", headers={"WWW-Authenticate": "Bearer"})
    try:
        subscription = broker.subscribe(current_user.id)
    except TooManyStreams:
        raise HTTPException(status_code=429, detail="Too many open chat event streams.") from None
    return StreamingResponse(
        _frames(
            broker,
            subscription,
            expires_at=current_user.expires_at,
            clock=clock,
            keepalive_seconds=timing.keepalive_seconds,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
