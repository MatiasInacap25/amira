"""Public handler guards and rollback paths not exercised by the happy-path suites."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response, UploadFile

from amira_api import chat_routes, customer_routes, location_routes, provider_service_routes, public_routes
from amira_api.chat_schemas import ChatMessageCreate
from amira_api.evidence_storage import EvidenceStorageError
from amira_api.public_schemas import ProviderServiceDriverAssignmentRequest, ServiceRequestCreate
from amira_api.settings import Settings
from test_account_provisioning import identity


def result(value):
    return NS(one_or_none=lambda: value, scalar_one_or_none=lambda: value,
              scalars=lambda: NS(all=lambda: value), mappings=lambda: NS(all=lambda: value))


@pytest.mark.parametrize("action", ["message", "upload", "read"])
def test_unknown_account_cannot_use_chat_message_or_attachment(monkeypatch, action):
    monkeypatch.setattr(chat_routes, "caller_account", lambda session, user: None)
    session, resolve = Mock(), Mock()
    with pytest.raises(HTTPException) as caught:
        if action == "message":
            chat_routes.send_chat_message(uuid4(), ChatMessageCreate(content="Hello"), identity(), session)
        elif action == "upload":
            chat_routes.send_chat_attachment(uuid4(), identity(), session, resolve, Settings(), UploadFile(BytesIO(b"photo")))
        else:
            chat_routes.get_chat_attachment_url(uuid4(), uuid4(), identity(), session, resolve, Settings())
    assert caught.value.status_code == 404
    session.execute.assert_not_called()
    resolve.assert_not_called()


def test_chat_attachment_signing_failure_is_translated(monkeypatch):
    monkeypatch.setattr(chat_routes, "caller_account", lambda session, user: NS(id=uuid4()))
    session, storage = Mock(), Mock()
    session.execute.side_effect = [result((uuid4(),)), result("private-key")]
    storage.create_signed_url.side_effect = EvidenceStorageError("private detail")
    with pytest.raises(HTTPException) as caught:
        chat_routes.get_chat_attachment_url(uuid4(), uuid4(), identity(), session, lambda: storage, Settings())
    assert caught.value.status_code == 502
    assert "private" not in caught.value.detail


@pytest.mark.parametrize("kind", ["customer", "provider"])
def test_delivery_photo_signing_failure_is_translated(monkeypatch, kind):
    module = customer_routes if kind == "customer" else provider_service_routes
    if kind == "customer":
        monkeypatch.setattr(module, "_customer_account_id", lambda session, user: uuid4())
        handler = module.get_customer_delivery_photo
    else:
        monkeypatch.setattr(module, "_provider_viewer", lambda session, user: NS(visibility=lambda: []))
        handler = module.get_provider_delivery_photo
    session, storage = Mock(), Mock()
    session.execute.return_value = result(("private-key",))
    storage.create_signed_url.side_effect = EvidenceStorageError("private detail")
    with pytest.raises(HTTPException) as caught:
        handler(uuid4(), identity(), session, lambda: storage, Settings())
    assert caught.value.status_code == 502
    session.commit.assert_not_called()


def test_unprovisioned_customer_quote_request_is_forbidden():
    payload = ServiceRequestCreate(profileId=uuid4(), serviceTypeId=uuid4(), origin="A", destination="B",
                                  originCommuneCode="13101", destinationCommuneCode="05101")
    session = Mock()
    session.execute.return_value = result(None)
    with pytest.raises(HTTPException) as caught:
        public_routes.create_service_request(payload, identity(), session)
    assert caught.value.status_code == 403
    session.commit.assert_not_called()


def test_unprovisioned_provider_request_list_is_forbidden():
    session = Mock()
    session.execute.return_value = result(None)
    with pytest.raises(HTTPException) as caught:
        public_routes.list_provider_requests(identity(), session)
    assert caught.value.status_code == 403


@pytest.mark.parametrize("status, decision, chats", [("accepted", "accept", []), ("rejected", "reject", [NS(id=uuid4())]), ("pending", "accept", [NS(id=uuid4())])])
def test_provider_request_inconsistent_chat_state_cannot_be_decided(monkeypatch, status, decision, chats):
    monkeypatch.setattr(public_routes, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    request_id = uuid4()
    request = NS(id=request_id, status=status)
    session = Mock()
    session.execute.side_effect = [result(request), result(chats)]
    with pytest.raises(HTTPException) as caught:
        getattr(public_routes, f"{decision}_provider_request")(request_id, identity(), session)
    assert caught.value.status_code == 409
    assert request.status == status
    session.commit.assert_not_called()


def test_provider_request_commit_failure_rolls_back(monkeypatch):
    monkeypatch.setattr(public_routes, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    request = NS(id=uuid4(), customer_id=uuid4(), status="pending")
    session = Mock()
    session.execute.side_effect = [result(request), result([])]
    session.commit.side_effect = RuntimeError("database offline")
    with pytest.raises(RuntimeError, match="offline"):
        public_routes.accept_provider_request(request.id, identity(), session)
    session.rollback.assert_called_once()


def test_provider_driver_assignment_missing_service_is_not_found(monkeypatch):
    monkeypatch.setattr(public_routes, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    session = Mock()
    session.execute.return_value = result(None)
    with pytest.raises(HTTPException) as caught:
        public_routes.assign_provider_service_driver(uuid4(), ProviderServiceDriverAssignmentRequest(driverId=uuid4()), identity(), session)
    assert caught.value.status_code == 404
    session.commit.assert_not_called()


def test_location_catalog_keeps_regions_without_communes():
    session = Mock()
    session.execute.return_value = result([dict(region_code="13", region_name="Metropolitana", commune_code=None, commune_name=None)])
    response = Response()
    catalog = location_routes.list_locations(response, session)
    assert catalog.regions[0].communes == []
    assert response.headers["Cache-Control"] == "public, max-age=3600"


def test_chat_attachment_failed_cleanup_does_not_hide_original_error(monkeypatch, caplog):
    monkeypatch.setattr(chat_routes, "caller_account", lambda session, user: NS(id=uuid4()))
    monkeypatch.setattr(chat_routes, "publish_chat_event", Mock())
    session, storage = Mock(), Mock()
    session.execute.return_value = result((uuid4(),))
    session.commit.side_effect = RuntimeError("database offline")
    storage.delete.side_effect = EvidenceStorageError("delete unavailable")
    with pytest.raises(RuntimeError, match="database offline"):
        chat_routes.send_chat_attachment(uuid4(), identity(), session, lambda: storage, Settings(),
                                        UploadFile(BytesIO(b"\xff\xd8\xffphoto")))
    storage.delete.assert_called_once_with(storage.upload.call_args.args[0])
    session.rollback.assert_called_once()
    assert "unreferenced chat photo" in caplog.text


def test_assignments_without_service_date_skip_conflict_query(monkeypatch):
    from amira_api.provider_service_routes import ServiceAssignmentsUpdate
    viewer = NS(is_owner=True, owned_profile_id=uuid4(), user_id=uuid4())
    service = NS(status="confirmed", service_at=None)
    expected = object()
    monkeypatch.setattr(provider_service_routes, "_provider_viewer", lambda session, user: viewer)
    monkeypatch.setattr(provider_service_routes, "_lock_visible_service", lambda session, viewer, identifier: service)
    monkeypatch.setattr(provider_service_routes, "_ensure_drivers_belong", Mock())
    monkeypatch.setattr(provider_service_routes, "_ensure_drivers_verified", Mock())
    monkeypatch.setattr(provider_service_routes, "_ensure_vehicles_belong", Mock())
    monkeypatch.setattr(provider_service_routes, "_visible_detail", lambda session, viewer, identifier: expected)
    session = Mock()
    payload = ServiceAssignmentsUpdate(assignments=[dict(driverId=uuid4(), vehicleId=uuid4())])
    assert provider_service_routes.replace_service_assignments(uuid4(), payload, identity(), session) is expected
    assert session.execute.call_count == 1  # Only the replacement DELETE, no same-day SELECT.
    session.commit.assert_called_once()
