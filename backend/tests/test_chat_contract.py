"""Pins the chat messages response shape that the frontend parses from the shared fixture."""

from __future__ import annotations

import json
from pathlib import Path

from amira_api.chat_schemas import ChatMessagesPage

FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "tests" / "fixtures" / "chat-messages-page.json"


def test_shared_thread_fixture_validates_and_round_trips_unchanged():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))

    page = ChatMessagesPage.model_validate(fixture)

    assert page.model_dump(by_alias=True, mode="json") == fixture
