"""Storage composition roots and compensating actions on route failure."""

from io import BytesIO
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError

from amira_api import evidence_storage as evidence, request_image_routes as images, vehicle_routes as vehicles
from amira_api.settings import Settings
from test_account_provisioning import identity

JPEG = b"\xff\xd8\xff" + b"x" * 20


def result(value):
    return NS(scalar_one_or_none=lambda: value, scalar_one=lambda: value, scalars=lambda: NS(all=lambda: value),
              all=lambda: value, mappings=lambda: NS(one_or_none=lambda: value))


@pytest.mark.parametrize("kind", ["evidence", "chat", "request", "vehicle"])
@pytest.mark.parametrize("configured", [False, True])
def test_storage_composition_resolves_only_configured_private_bucket(monkeypatch, kind, configured):
    adapter = object()
    factory = Mock(return_value=adapter)
    monkeypatch.setattr(evidence, "_supabase_storage", factory)
    monkeypatch.setattr(vehicles, "_supabase_storage", factory)
    settings = Settings(supabase_url="https://storage.test", supabase_service_role_key="test-secret", request_images_bucket="request-images", vehicle_images_bucket="vehicle-images") if configured else Settings()
    resolvers = {"evidence": evidence.get_evidence_storage_resolver, "chat": evidence.get_chat_attachment_storage_resolver,
                 "request": evidence.get_request_image_storage_resolver, "vehicle": vehicles.get_vehicle_image_storage_resolver}
    resolve = resolvers[kind](settings)
    factory.assert_not_called()
    if configured:
        assert resolve() is adapter
        assert factory.call_args.args[:2] == ("https://storage.test", "test-secret")
    else:
        with pytest.raises(HTTPException) as caught:
            resolve()
        assert caught.value.status_code == 503
        factory.assert_not_called()


@pytest.mark.parametrize("failure", ["size", "duplicate", "integrity", "unexpected", "cleanup"])
def test_vehicle_upload_error_paths_cleanup_and_transaction_state(monkeypatch, failure):
    profile_id = uuid4()
    monkeypatch.setattr(vehicles, "_owned_provider", lambda session, user: (uuid4(), profile_id))
    session, storage = Mock(), Mock()
    session.execute.return_value = result(uuid4() if failure == "duplicate" else None)
    if failure in {"integrity", "cleanup"}:
        session.commit.side_effect = IntegrityError("insert", {}, Exception("unique"))
    elif failure == "unexpected":
        session.commit.side_effect = RuntimeError("database unavailable")
    if failure == "cleanup":
        storage.delete.side_effect = evidence.EvidenceStorageError("delete unavailable")
    config = Settings(chat_attachment_max_bytes=1 if failure == "size" else 1024)
    error = RuntimeError if failure == "unexpected" else HTTPException
    with pytest.raises(error) as caught:
        vehicles.create_vehicle(identity(), session, lambda: storage, config, " AB12 ", " Brand ", " Model ",
                                UploadFile(BytesIO(JPEG)), year=None, maximum_weight=None)
    if failure != "unexpected":
        assert caught.value.status_code == {"size": 413, "duplicate": 409, "integrity": 409, "cleanup": 409}[failure]
    if failure in {"size", "duplicate"}:
        storage.upload.assert_not_called()
        session.commit.assert_not_called()
    else:
        assert session.rollback.call_count == 2
        storage.delete.assert_called_once_with(storage.upload.call_args.args[0])


def test_vehicle_signed_url_failure_is_translated(monkeypatch):
    monkeypatch.setattr(vehicles, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    session, storage = Mock(), Mock()
    session.execute.return_value = result([NS(image_storage_key="private-key")])
    storage.create_signed_url.side_effect = evidence.EvidenceStorageError("private failure")
    with pytest.raises(HTTPException) as caught:
        vehicles.list_vehicles(identity(), session, lambda: storage, Settings())
    assert caught.value.status_code == 502
    assert "private" not in caught.value.detail
    session.commit.assert_not_called()


def test_vehicle_delete_integrity_failure_keeps_photo(monkeypatch):
    monkeypatch.setattr(vehicles, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    session, storage = Mock(), Mock()
    session.execute.side_effect = [result(NS(image_storage_key="private-key")), result(0), result(0), result(0)]
    session.commit.side_effect = IntegrityError("delete", {}, Exception("foreign key"))
    with pytest.raises(HTTPException) as caught:
        vehicles.delete_vehicle(uuid4(), identity(), session, lambda: storage)
    assert caught.value.status_code == 409
    session.rollback.assert_called_once()
    storage.delete.assert_not_called()


@pytest.mark.parametrize("failure", ["missing-account", "upload", "lost-owner", "commit", "cleanup"])
def test_request_upload_error_paths_preserve_consistency(monkeypatch, failure):
    monkeypatch.setattr(images, "caller_account", lambda session, user: None if failure == "missing-account" else NS(id=uuid4()))
    session, storage = Mock(), Mock()
    session.execute.side_effect = [result(uuid4()), result(0), result(None if failure == "lost-owner" else uuid4()), result(0)]
    if failure == "upload":
        storage.upload.side_effect = evidence.EvidenceStorageError("upload unavailable")
    if failure in {"commit", "cleanup"}:
        session.commit.side_effect = RuntimeError("database unavailable")
    if failure == "cleanup":
        storage.delete.side_effect = evidence.EvidenceStorageError("delete unavailable")
    error = RuntimeError if failure in {"commit", "cleanup"} else HTTPException
    with pytest.raises(error) as caught:
        images.upload_request_image(uuid4(), identity(), session, lambda: storage, Settings(), UploadFile(BytesIO(JPEG)))
    if failure not in {"commit", "cleanup"}:
        assert caught.value.status_code == {"missing-account": 404, "upload": 502, "lost-owner": 404}[failure]
    if failure in {"lost-owner", "commit", "cleanup"}:
        storage.delete.assert_called_once_with(storage.upload.call_args.args[0])
        assert session.rollback.call_count == 2
    elif failure == "missing-account":
        storage.upload.assert_not_called()


@pytest.mark.parametrize("visible, keys, fails", [(None, [], False), ({}, [], False), ({}, [(uuid4(), "key")], True)])
def test_provider_request_photo_visibility_empty_list_and_signing_failure(monkeypatch, visible, keys, fails):
    monkeypatch.setattr(images, "caller_account", lambda session, user: None)
    monkeypatch.setattr(images, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    session, storage = Mock(), Mock()
    session.execute.side_effect = [result(visible), result(keys)]
    storage.create_signed_url.side_effect = evidence.EvidenceStorageError("private failure")
    if visible is None or fails:
        with pytest.raises(HTTPException) as caught:
            images.list_request_images(uuid4(), identity(), session, lambda: storage, Settings())
        assert caught.value.status_code == (404 if visible is None else 502)
    else:
        assert images.list_request_images(uuid4(), identity(), session, lambda: storage, Settings()).items == []
        storage.create_signed_url.assert_not_called()


def test_vehicle_blank_fields_are_rejected_before_storage(monkeypatch):
    monkeypatch.setattr(vehicles, "_owned_provider", lambda session, user: (uuid4(), uuid4()))
    session, resolve = Mock(), Mock()
    with pytest.raises(HTTPException) as caught:
        vehicles.create_vehicle(identity(), session, resolve, Settings(), " ", "Brand", "Model", UploadFile(BytesIO(JPEG)))
    assert caught.value.status_code == 422
    resolve.assert_not_called()
    session.commit.assert_not_called()


def test_storage_adapter_constructor_uses_private_bucket_without_network(monkeypatch):
    from amira_api import supabase_evidence_storage
    factory = Mock(return_value=object())
    monkeypatch.setattr(supabase_evidence_storage, "SupabaseEvidenceStorage", factory)
    evidence._supabase_storage.cache_clear()
    try:
        storage = evidence.get_evidence_storage(Settings(supabase_url="https://storage.test", supabase_service_role_key="secret", service_evidence_bucket="private-evidence"))
        assert storage is factory.return_value
        factory.assert_called_once_with(base_url="https://storage.test", service_role_key="secret", bucket="private-evidence")
    finally:
        evidence._supabase_storage.cache_clear()
