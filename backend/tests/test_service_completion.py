"""Completing a service with a delivery photo, and reading that photo through a short-lived signed URL.

Storage is an in-memory fake behind the EvidenceStorage port. The Supabase adapter has its own tests, so no test
reaches the network. Only an assigned driver can complete; the owner who is not assigned gets 403, and a viewer who
cannot see the service gets 404.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import as_utc, utc_now
from amira_api.db import get_db_session
from amira_api.evidence_storage import EvidenceStorageError, get_evidence_storage, get_evidence_storage_resolver
from amira_api.main import app
from amira_api.models import RolUsuario, Servicio, Usuario
from amira_api.settings import Settings, get_settings
from test_provider_service_actions import GUS_AUTH, OUTSIDER_AUTH, Fleet, fleet  # noqa: F401  (fixture re-export)
from test_provider_service_routes import (  # noqa: F401  (pytest fixture re-export)
    CUSTOMER_AUTH,
    EMPLOYED_DRIVER_AUTH,
    INDEPENDENT_AUTH,
    OTHER_CUSTOMER_AUTH,
    OWNER_AUTH,
    db,
)

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
WEBP = b"RIFF" + b"\x24\x00\x00\x00" + b"WEBPVP8 " + b"\x00" * 64
SIGNED_BASE = "https://storage.example.test"


class FakeEvidenceStorage:
    def __init__(self) -> None:
        self.fail_upload = False
        self.fail_delete = False
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.signed: list[tuple[str, int]] = []
        # Runs inside upload, after the bytes are accepted, to simulate another request acting meanwhile.
        self.on_upload: Callable[[], None] | None = None

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise EvidenceStorageError("storage unavailable")
        self.uploads[key] = (content, content_type)
        if self.on_upload is not None:
            self.on_upload()

    def delete(self, key: str) -> None:
        if self.fail_delete:
            raise EvidenceStorageError("storage unavailable")
        self.deleted.append(key)

    def create_signed_url(self, key: str, expires_in: int) -> str:
        self.signed.append((key, expires_in))
        return f"{SIGNED_BASE}/{key}?token=signed"


@dataclass
class Api:
    client: TestClient
    storage: FakeEvidenceStorage
    settings_kwargs: dict = field(default_factory=dict)

    def request(self, method: str, path: str, *, as_auth_id, **kwargs):
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=as_auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )
        return self.client.request(method, path, **kwargs)


@pytest.fixture
def storage() -> FakeEvidenceStorage:
    return FakeEvidenceStorage()


@pytest.fixture
def api(db: Session, storage: FakeEvidenceStorage):
    settings_kwargs: dict = {}
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_evidence_storage] = lambda: storage
    app.dependency_overrides[get_evidence_storage_resolver] = lambda: (lambda: storage)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **settings_kwargs)
    yield Api(TestClient(app), storage, settings_kwargs)
    for dependency in (get_db_session, get_current_user, get_evidence_storage, get_evidence_storage_resolver, get_settings):
        app.dependency_overrides.pop(dependency, None)


def _start(db: Session, service: Servicio) -> None:
    service.status = "in_progress"
    service.starts_at = utc_now()
    db.commit()


def _complete(api: Api, service: Servicio, *, auth=EMPLOYED_DRIVER_AUTH, content=JPEG,
              filename="evidence.jpg", content_type="image/jpeg"):
    return api.request(
        "POST",
        f"/api/provider/services/{service.id}/complete",
        as_auth_id=auth,
        files={"photo": (filename, content, content_type)},
    )


def _utc(value: str) -> datetime:
    return as_utc(datetime.fromisoformat(value))


def _stored_service(db: Session, service: Servicio) -> Servicio:
    db.expire_all()
    return db.execute(select(Servicio).where(Servicio.id == service.id)).scalar_one()


# --- POST /complete ----------------------------------------------------------------------------------------------------


def test_assigned_driver_completes_with_the_photo_and_sets_the_timestamps_and_deadline(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    before = utc_now()

    response = _complete(api, fleet.service_a)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["deliveryPhotoAvailable"] is True
    row = _stored_service(db, fleet.service_a)
    assert row.status == "completed"
    assert row.delivery_evidence_key.startswith(f"services/{fleet.service_a.id}/")
    assert row.delivery_evidence_key.endswith(".jpg")
    assert as_utc(row.completed_at) >= before
    assert as_utc(row.completion_notified_at) == as_utc(row.completed_at)
    assert as_utc(row.payout_deadline_at) == as_utc(row.completed_at) + timedelta(hours=24)
    assert _utc(body["completedAt"]) == as_utc(row.completed_at)
    assert _utc(body["payoutDeadlineAt"]) == as_utc(row.payout_deadline_at)


def test_the_photo_is_stored_under_a_server_generated_key_with_its_content_type(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, filename="../../etc/mi foto.jpg")

    assert response.status_code == 200
    key = _stored_service(db, fleet.service_a).delivery_evidence_key
    assert "mi foto" not in key and ".." not in key
    assert api.storage.uploads == {key: (JPEG, "image/jpeg")}


@pytest.mark.parametrize(("content", "content_type", "extension"), [
    (JPEG, "image/jpeg", "jpg"),
    (PNG, "image/png", "png"),
    (WEBP, "image/webp", "webp"),
])
def test_jpeg_png_and_webp_are_accepted(api, db, fleet: Fleet, content, content_type, extension):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, content=content, content_type=content_type)

    assert response.status_code == 200
    assert _stored_service(db, fleet.service_a).delivery_evidence_key.endswith(f".{extension}")


def test_completion_never_exposes_the_storage_key_or_a_signed_url(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a)

    key = _stored_service(db, fleet.service_a).delivery_evidence_key
    assert key not in response.text
    assert "token=" not in response.text
    assert "deliveryEvidenceKey" not in response.json()


def test_owner_who_is_not_assigned_gets_403_and_nothing_is_written(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, auth=OWNER_AUTH)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only an assigned driver can complete this service."
    row = _stored_service(db, fleet.service_a)
    assert row.status == "in_progress" and row.delivery_evidence_key is None
    assert api.storage.uploads == {}


@pytest.mark.parametrize("auth", [OUTSIDER_AUTH, GUS_AUTH, INDEPENDENT_AUTH])
def test_viewers_who_cannot_see_the_service_get_404(api, db, fleet: Fleet, auth):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, auth=auth)

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."
    assert api.storage.uploads == {}


def test_customer_gets_403_on_the_provider_completion_route(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, auth=CUSTOMER_AUTH)

    assert response.status_code == 403
    assert response.json()["detail"] == "Only provider accounts can access provider services."


def test_a_service_that_is_not_in_progress_is_409(api, db, fleet: Fleet):
    response = _complete(api, fleet.service_a)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only in-progress services can be completed."
    assert api.storage.uploads == {}


def test_completing_twice_is_409_and_keeps_the_first_photo(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    first = _complete(api, fleet.service_a)
    first_key = _stored_service(db, fleet.service_a).delivery_evidence_key

    second = _complete(api, fleet.service_a, content=PNG, content_type="image/png")

    assert first.status_code == 200
    assert second.status_code == 409
    assert _stored_service(db, fleet.service_a).delivery_evidence_key == first_key
    assert len(api.storage.uploads) == 1


def test_a_text_file_declared_as_png_is_415_by_magic_bytes(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, content=b"not an image at all",
                         filename="evidence.png", content_type="image/png")

    assert response.status_code == 415
    assert response.json()["detail"] == "The delivery photo must be a JPEG, PNG or WebP image."
    row = _stored_service(db, fleet.service_a)
    assert row.status == "in_progress" and row.delivery_evidence_key is None
    assert api.storage.uploads == {}


def test_a_photo_over_the_size_cap_is_413_and_nothing_is_stored(api, db, fleet: Fleet):
    api.settings_kwargs["service_evidence_max_bytes"] = 100
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a, content=JPEG + b"\x00" * 100)

    assert response.status_code == 413
    assert response.json()["detail"] == "The delivery photo is larger than the allowed size."
    assert _stored_service(db, fleet.service_a).status == "in_progress"
    assert api.storage.uploads == {}


def test_a_photo_exactly_at_the_size_cap_is_accepted(api, db, fleet: Fleet):
    api.settings_kwargs["service_evidence_max_bytes"] = len(JPEG)
    _start(db, fleet.service_a)

    assert _complete(api, fleet.service_a).status_code == 200


def test_storage_failure_is_502_and_writes_nothing(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    api.storage.fail_upload = True

    response = _complete(api, fleet.service_a)

    assert response.status_code == 502
    assert response.json()["detail"] == "The delivery photo could not be stored. Try again."
    row = _stored_service(db, fleet.service_a)
    assert row.status == "in_progress"
    assert row.delivery_evidence_key is None
    assert row.completed_at is None
    assert row.completion_notified_at is None
    assert row.payout_deadline_at is None


def test_the_claim_window_setting_drives_the_payout_deadline(api, db, fleet: Fleet):
    api.settings_kwargs["service_claim_window_hours"] = 6
    _start(db, fleet.service_a)

    response = _complete(api, fleet.service_a)

    assert response.status_code == 200
    row = _stored_service(db, fleet.service_a)
    assert as_utc(row.payout_deadline_at) - as_utc(row.completed_at) == timedelta(hours=6)


def test_a_missing_photo_field_is_422(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    response = api.request("POST", f"/api/provider/services/{fleet.service_a.id}/complete",
                           as_auth_id=EMPLOYED_DRIVER_AUTH)

    assert response.status_code == 422
    assert _stored_service(db, fleet.service_a).status == "in_progress"


# --- GET /delivery-photo -----------------------------------------------------------------------------------------------


def _provider_photo(api: Api, service: Servicio, auth=OWNER_AUTH):
    return api.request("GET", f"/api/provider/services/{service.id}/delivery-photo", as_auth_id=auth)


def _customer_photo(api: Api, service: Servicio, auth=CUSTOMER_AUTH):
    return api.request("GET", f"/api/customer/services/{service.id}/delivery-photo", as_auth_id=auth)


def test_delivery_photo_is_404_before_the_service_is_completed(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    provider = _provider_photo(api, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH)
    customer = _customer_photo(api, fleet.service_a)

    assert provider.status_code == 404
    assert provider.json()["detail"] == "Delivery photo not found."
    assert customer.status_code == 404
    assert customer.json()["detail"] == "Delivery photo not found."
    assert api.storage.signed == []


def test_detail_reports_photo_availability_for_the_customer_and_provider(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    customer_before = api.request("GET", f"/api/customer/services/{fleet.service_a.id}", as_auth_id=CUSTOMER_AUTH)
    _complete(api, fleet.service_a)
    customer_after = api.request("GET", f"/api/customer/services/{fleet.service_a.id}", as_auth_id=CUSTOMER_AUTH)
    provider_after = api.request("GET", f"/api/provider/services/{fleet.service_a.id}", as_auth_id=OWNER_AUTH)

    assert customer_before.json()["deliveryPhotoAvailable"] is False
    assert customer_after.json()["deliveryPhotoAvailable"] is True
    assert provider_after.json()["deliveryPhotoAvailable"] is True


def test_owner_driver_and_customer_get_a_short_lived_signed_url(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    _complete(api, fleet.service_a)
    key = _stored_service(db, fleet.service_a).delivery_evidence_key
    before = utc_now()

    owner = _provider_photo(api, fleet.service_a, auth=OWNER_AUTH)
    driver = _provider_photo(api, fleet.service_a, auth=EMPLOYED_DRIVER_AUTH)
    customer = _customer_photo(api, fleet.service_a)

    for response in (owner, driver, customer):
        assert response.status_code == 200
        body = response.json()
        assert body["url"] == f"{SIGNED_BASE}/{key}?token=signed"
        assert before + timedelta(seconds=299) <= _utc(body["expiresAt"]) <= utc_now() + timedelta(seconds=300)
    assert api.storage.signed == [(key, 300), (key, 300), (key, 300)]


def test_signed_url_ttl_comes_from_settings(api, db, fleet: Fleet):
    api.settings_kwargs["service_evidence_url_ttl_seconds"] = 60
    _start(db, fleet.service_a)
    _complete(api, fleet.service_a)

    assert _provider_photo(api, fleet.service_a).status_code == 200
    assert api.storage.signed[-1][1] == 60


def test_another_customer_gets_404_for_the_delivery_photo(api, db, fleet: Fleet):
    client_role = db.execute(select(RolUsuario).where(RolUsuario.code == "client")).scalar_one()
    db.add(Usuario(id=uuid4(), auth_user_id=OTHER_CUSTOMER_AUTH, first_name="Xavi", last_name="Other",
                   email="xavi@example.test", role_id=client_role.id))
    db.commit()
    _start(db, fleet.service_a)
    _complete(api, fleet.service_a)

    response = _customer_photo(api, fleet.service_a, auth=OTHER_CUSTOMER_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."
    assert api.storage.signed == []


def test_unseen_provider_gets_404_for_the_delivery_photo(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    _complete(api, fleet.service_a)

    response = _provider_photo(api, fleet.service_a, auth=OUTSIDER_AUTH)

    assert response.status_code == 404
    assert response.json()["detail"] == "Service not found."


# --- Upload outside the row lock, cleanup of an orphaned photo, storage resolved after the checks ----------------------


def test_the_photo_is_uploaded_without_holding_the_service_row_lock(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    in_transaction_during_upload: list[bool] = []
    api.storage.on_upload = lambda: in_transaction_during_upload.append(db.in_transaction())

    response = _complete(api, fleet.service_a)

    assert response.status_code == 200
    assert in_transaction_during_upload == [False]
    assert api.storage.deleted == []


def test_a_photo_is_deleted_when_the_service_changed_while_it_was_uploading(api, db, fleet: Fleet):
    _start(db, fleet.service_a)

    def cancel_meanwhile() -> None:
        db.execute(update(Servicio).where(Servicio.id == fleet.service_a.id).values(status="disputed"))
        db.commit()

    api.storage.on_upload = cancel_meanwhile

    response = _complete(api, fleet.service_a)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only in-progress services can be completed."
    assert len(api.storage.uploads) == 1
    assert api.storage.deleted == list(api.storage.uploads)
    row = _stored_service(db, fleet.service_a)
    assert row.status == "disputed"
    assert row.delivery_evidence_key is None


def test_a_failed_cleanup_does_not_mask_the_conflict_response(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    api.storage.fail_delete = True

    def cancel_meanwhile() -> None:
        db.execute(update(Servicio).where(Servicio.id == fleet.service_a.id).values(status="disputed"))
        db.commit()

    api.storage.on_upload = cancel_meanwhile

    response = _complete(api, fleet.service_a)

    assert response.status_code == 409
    assert response.json()["detail"] == "Only in-progress services can be completed."


def test_a_commit_failure_after_the_upload_deletes_the_photo_and_writes_nothing(api, db, fleet: Fleet, monkeypatch):
    _start(db, fleet.service_a)

    def failing_commit() -> None:
        raise RuntimeError("database connection lost")

    monkeypatch.setattr(db, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="database connection lost"):
        _complete(api, fleet.service_a)
    monkeypatch.undo()

    assert len(api.storage.uploads) == 1
    assert api.storage.deleted == list(api.storage.uploads)
    row = _stored_service(db, fleet.service_a)
    assert row.status == "in_progress"
    assert row.delivery_evidence_key is None


def test_unconfigured_storage_raises_503_with_the_documented_message():
    with pytest.raises(HTTPException) as error:
        get_evidence_storage(Settings(_env_file=None, supabase_url=None))

    assert error.value.status_code == 503
    assert error.value.detail == "Delivery photo storage is not configured."


def test_storage_is_resolved_after_the_visibility_and_assignment_checks(api, db, fleet: Fleet):
    api.settings_kwargs["supabase_url"] = None
    app.dependency_overrides.pop(get_evidence_storage_resolver, None)
    _start(db, fleet.service_a)

    unseen = _complete(api, fleet.service_a, auth=OUTSIDER_AUTH)
    not_assigned = _complete(api, fleet.service_a, auth=OWNER_AUTH)
    assigned = _complete(api, fleet.service_a)

    assert unseen.status_code == 404
    assert not_assigned.status_code == 403
    assert assigned.status_code == 503
    assert assigned.json()["detail"] == "Delivery photo storage is not configured."
    assert _stored_service(db, fleet.service_a).status == "in_progress"


def _unconfigure_storage(api: Api) -> None:
    api.settings_kwargs["supabase_url"] = None
    app.dependency_overrides.pop(get_evidence_storage, None)
    app.dependency_overrides.pop(get_evidence_storage_resolver, None)


def test_photo_reads_answer_404_before_503_when_storage_is_unconfigured(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    _unconfigure_storage(api)

    unseen = _provider_photo(api, fleet.service_a, auth=OUTSIDER_AUTH)
    provider_without_photo = _provider_photo(api, fleet.service_a)
    customer_without_photo = _customer_photo(api, fleet.service_a)

    assert unseen.status_code == 404
    assert unseen.json()["detail"] == "Service not found."
    assert provider_without_photo.status_code == 404
    assert provider_without_photo.json()["detail"] == "Delivery photo not found."
    assert customer_without_photo.status_code == 404
    assert customer_without_photo.json()["detail"] == "Delivery photo not found."
    assert api.storage.signed == []


def test_a_visible_photo_read_is_503_when_storage_is_unconfigured(api, db, fleet: Fleet):
    _start(db, fleet.service_a)
    _complete(api, fleet.service_a)
    _unconfigure_storage(api)

    provider = _provider_photo(api, fleet.service_a)
    customer = _customer_photo(api, fleet.service_a)

    assert provider.status_code == 503
    assert customer.status_code == 503
    assert provider.json()["detail"] == "Delivery photo storage is not configured."
    assert customer.json()["detail"] == "Delivery photo storage is not configured."
    assert api.storage.signed == []
