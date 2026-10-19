"""Image attachments in chat: upload, timeline entry, signed read URL, list preview and failure handling."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.evidence_storage import EvidenceStorageError, get_chat_attachment_storage_resolver
from amira_api.main import app
from amira_api.models import Mensaje
from amira_api.realtime import CHAT_EVENTS_CHANNEL
from amira_api.settings import Settings, get_settings
from chat_support import CUSTOMER_AUTH, OTHER_CUSTOMER_AUTH, PROVIDER_AUTH, Scenario, db, scenario  # noqa: F401

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBPVP8 " + b"\x00" * 64
SIGNED_BASE = "https://storage.example.test"
MAX_BYTES = 5 * 1024 * 1024
CONFIGURED = {"supabase_url": "https://project.example.test", "supabase_service_role_key": "service-role-test"}


class FakeChatStorage:
    def __init__(self) -> None:
        self.fail_upload = False
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.signed: list[tuple[str, int]] = []

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise EvidenceStorageError("storage unavailable")
        self.uploads[key] = (content, content_type)

    def delete(self, key: str) -> None:
        self.deleted.append(key)

    def create_signed_url(self, key: str, expires_in: int) -> str:
        self.signed.append((key, expires_in))
        return f"{SIGNED_BASE}/{key}?token=signed"


@dataclass
class ChatApi:
    client: TestClient
    storage: FakeChatStorage
    _settings: dict = field(default_factory=lambda: dict(CONFIGURED))

    def request(self, method: str, path: str, *, as_auth_id: UUID, **kwargs):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return self.client.request(method, path, **kwargs)

    def configure(self, **overrides) -> None:
        self._settings = {**CONFIGURED, **overrides}
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **self._settings)

    def upload(self, chat_id: UUID, *, as_auth_id: UUID, photo: bytes = JPEG, content_type: str = "image/jpeg", **data):
        return self.request(
            "POST",
            f"/api/chats/{chat_id}/messages/attachments",
            as_auth_id=as_auth_id,
            files={"photo": ("photo.bin", photo, content_type)},
            data=data,
        )


@pytest.fixture
def storage() -> FakeChatStorage:
    return FakeChatStorage()


@pytest.fixture
def api(db: Session, storage: FakeChatStorage):
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_chat_attachment_storage_resolver] = lambda: (lambda: storage)
    chat_api = ChatApi(client=TestClient(app), storage=storage)
    chat_api.configure()
    yield chat_api
    for dependency in (get_db_session, get_current_user, get_chat_attachment_storage_resolver, get_settings):
        app.dependency_overrides.pop(dependency, None)


def _attachments_in(db: Session) -> list[Mensaje]:
    return db.query(Mensaje).filter(Mensaje.attachment_key.is_not(None)).all()


def test_participant_upload_stores_the_photo_and_returns_the_timeline_entry(api, db: Session, scenario: Scenario, storage):
    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, content="Así quedó el sofá")

    assert response.status_code == 201
    body = response.json()
    assert body["kind"] == "message"
    assert body["content"] == "Así quedó el sofá"
    assert body["fromMe"] is True
    assert body["attachment"] == {"contentType": "image/jpeg", "sizeBytes": len(JPEG)}

    message_id = UUID(body["messageId"])
    key = f"chats/{scenario.chat_a.id}/{message_id}.jpg"
    assert storage.uploads == {key: (JPEG, "image/jpeg")}
    stored = db.get(Mensaje, message_id)
    assert stored.attachment_key == key
    assert stored.attachment_content_type == "image/jpeg"
    assert stored.attachment_size_bytes == len(JPEG)


def test_image_only_message_stores_empty_text(api, db: Session, scenario: Scenario):
    response = api.upload(scenario.chat_a.id, as_auth_id=PROVIDER_AUTH)

    assert response.status_code == 201
    assert response.json()["content"] == ""
    assert db.get(Mensaje, UUID(response.json()["messageId"])).content == ""


def test_jpeg_png_and_webp_are_accepted_and_keep_their_extension(api, scenario: Scenario, storage):
    for photo, content_type, extension in ((PNG, "image/png", "png"), (WEBP, "image/webp", "webp")):
        response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, photo=photo, content_type=content_type)

        assert response.status_code == 201
        assert response.json()["attachment"]["contentType"] == content_type
        assert any(key.endswith(f".{extension}") for key in storage.uploads)


def test_the_upload_publishes_message_created_in_the_same_transaction(api, db: Session, scenario: Scenario):
    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH)

    notifications = db.info["notifications"]
    assert [channel for channel, _ in notifications] == [CHAT_EVENTS_CHANNEL]
    _, payload = notifications[0]
    assert "message.created" in payload
    assert response.json()["messageId"] in payload


def test_non_participant_gets_404_and_nothing_is_uploaded(api, db: Session, scenario: Scenario, storage):
    response = api.upload(scenario.chat_a.id, as_auth_id=OTHER_CUSTOMER_AUTH)

    assert response.status_code == 404
    assert storage.uploads == {}
    assert _attachments_in(db) == []


def test_unknown_chat_gets_the_same_404(api, scenario: Scenario, storage):
    response = api.upload(uuid4(), as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 404
    assert storage.uploads == {}


@pytest.mark.parametrize("photo", [b"GIF89a" + b"\x00" * 64, b"%PDF-1.7 not a photo", b""])
def test_bytes_that_are_not_jpeg_png_or_webp_are_rejected(api, db: Session, scenario: Scenario, storage, photo):
    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, photo=photo, content_type="image/jpeg")

    assert response.status_code == 415
    assert storage.uploads == {}
    assert _attachments_in(db) == []


def test_a_declared_image_type_is_not_trusted_over_the_bytes(api, scenario: Scenario, storage):
    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, photo=b"plain text", content_type="image/png")

    assert response.status_code == 415
    assert storage.uploads == {}


def test_a_photo_over_five_mib_is_rejected_with_413(api, db: Session, scenario: Scenario, storage):
    oversized = JPEG + b"\x00" * (MAX_BYTES + 1 - len(JPEG))

    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, photo=oversized)

    assert response.status_code == 413
    assert storage.uploads == {}
    assert _attachments_in(db) == []


def test_a_photo_at_exactly_five_mib_is_accepted(api, scenario: Scenario):
    exact = JPEG + b"\x00" * (MAX_BYTES - len(JPEG))

    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, photo=exact)

    assert response.status_code == 201
    assert response.json()["attachment"]["sizeBytes"] == MAX_BYTES


def test_contact_details_in_the_caption_are_blocked_before_any_upload(api, db: Session, scenario: Scenario, storage):
    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, content="Llámame al +56911112222")

    assert response.status_code == 422
    assert response.json()["detail"][0]["type"] == "contact_details_blocked"
    assert "+56911112222" not in response.text
    assert storage.uploads == {}
    assert _attachments_in(db) == []


def test_a_caption_that_is_too_long_is_rejected(api, scenario: Scenario, storage):
    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, content="x" * 2001)

    assert response.status_code == 422
    assert storage.uploads == {}


def test_a_failed_database_write_deletes_the_uploaded_object(api, db: Session, scenario: Scenario, storage, monkeypatch):
    def fail_commit():
        raise RuntimeError("database went away")

    monkeypatch.setattr(db, "commit", fail_commit)

    with pytest.raises(RuntimeError):
        api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH)

    assert len(storage.uploads) == 1
    assert storage.deleted == list(storage.uploads)
    assert _attachments_in(db) == []


def test_a_failed_upload_writes_no_message(api, db: Session, scenario: Scenario, storage):
    storage.fail_upload = True

    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 502
    assert storage.deleted == []
    assert _attachments_in(db) == []


def test_without_storage_settings_the_upload_answers_503_and_writes_nothing(api, db: Session, scenario: Scenario):
    app.dependency_overrides.pop(get_chat_attachment_storage_resolver, None)
    api.configure(supabase_url=None, supabase_service_role_key=None)

    response = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 503
    assert _attachments_in(db) == []


def test_participant_gets_a_signed_url_valid_for_300_seconds(api, scenario: Scenario, storage):
    created = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH).json()

    response = api.request(
        "GET", f"/api/chats/{scenario.chat_a.id}/messages/{created['messageId']}/attachment", as_auth_id=PROVIDER_AUTH
    )

    assert response.status_code == 200
    body = response.json()
    assert body["url"].startswith(SIGNED_BASE)
    assert "expiresAt" in body
    assert storage.signed == [(next(iter(storage.uploads)), 300)]


def test_signed_url_is_404_for_a_non_participant(api, scenario: Scenario, storage):
    created = api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH).json()

    response = api.request(
        "GET", f"/api/chats/{scenario.chat_a.id}/messages/{created['messageId']}/attachment", as_auth_id=OTHER_CUSTOMER_AUTH
    )

    assert response.status_code == 404
    assert storage.signed == []


def test_signed_url_is_404_for_a_message_without_an_attachment(api, scenario: Scenario, storage):
    chat_id = scenario.chat_a.id
    plain = api.request("POST", f"/api/chats/{chat_id}/messages", as_auth_id=CUSTOMER_AUTH, json={"content": "Hola"}).json()

    response = api.request(
        "GET", f"/api/chats/{chat_id}/messages/{plain['messageId']}/attachment", as_auth_id=CUSTOMER_AUTH
    )

    assert response.status_code == 404
    assert storage.signed == []


def test_signed_url_is_404_for_an_unknown_message(api, scenario: Scenario, storage):
    response = api.request(
        "GET", f"/api/chats/{scenario.chat_a.id}/messages/{uuid4()}/attachment", as_auth_id=CUSTOMER_AUTH
    )

    assert response.status_code == 404


def test_timeline_entries_carry_the_attachment_or_null(api, scenario: Scenario):
    api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, content="Mira")

    timeline = api.request("GET", f"/api/chats/{scenario.chat_a.id}/messages", as_auth_id=CUSTOMER_AUTH).json()["timeline"]

    with_photo = [entry for entry in timeline if entry.get("attachment")]
    assert with_photo == [
        {
            "kind": "message",
            "messageId": with_photo[0]["messageId"],
            "content": "Mira",
            "sentAt": with_photo[0]["sentAt"],
            "fromMe": True,
            "senderName": "Casey Customer",
            "attachment": {"contentType": "image/jpeg", "sizeBytes": len(JPEG)},
        }
    ]
    text_entries = [entry for entry in timeline if entry["kind"] == "message" and not entry.get("attachment")]
    assert text_entries
    assert all(entry["attachment"] is None for entry in text_entries)


def test_chat_list_previews_an_image_only_last_message_as_foto(api, scenario: Scenario):
    api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH)

    items = api.request("GET", "/api/chats", as_auth_id=CUSTOMER_AUTH).json()["items"]

    preview = next(item for item in items if item["chatId"] == str(scenario.chat_a.id))["lastMessage"]
    assert preview["content"] == "Foto"
    assert preview["fromMe"] is True


def test_chat_list_keeps_the_text_of_a_captioned_last_message(api, scenario: Scenario):
    api.upload(scenario.chat_a.id, as_auth_id=CUSTOMER_AUTH, content="Llegó bien")

    items = api.request("GET", "/api/chats", as_auth_id=CUSTOMER_AUTH).json()["items"]

    preview = next(item for item in items if item["chatId"] == str(scenario.chat_a.id))["lastMessage"]
    assert preview["content"] == "Llegó bien"
