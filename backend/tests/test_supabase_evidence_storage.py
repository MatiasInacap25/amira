"""Supabase Storage adapter over httpx. A mock transport captures the requests, so nothing reaches the network."""

import json

import httpx
import pytest

from amira_api.evidence_storage import EvidenceStorageError
from amira_api.supabase_evidence_storage import SupabaseEvidenceStorage

BASE_URL = "https://project.supabase.co"
SERVICE_KEY = "service-role-test-key"
BUCKET = "service-evidence"
OBJECT_KEY = "services/0c9a4d2e-1111-4222-8333-444455556666/7f0e1d2c-aaaa-bbbb-cccc-ddddeeeeffff.jpg"


def _storage(handler) -> SupabaseEvidenceStorage:
    return SupabaseEvidenceStorage(
        base_url=BASE_URL,
        service_role_key=SERVICE_KEY,
        bucket=BUCKET,
        transport=httpx.MockTransport(handler),
    )


def test_upload_posts_the_bytes_to_the_bucket_with_the_service_role_key() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": f"{BUCKET}/{OBJECT_KEY}"})

    _storage(handler).upload(OBJECT_KEY, b"\xff\xd8\xff photo", "image/jpeg")

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/storage/v1/object/{BUCKET}/{OBJECT_KEY}"
    assert request.headers["authorization"] == f"Bearer {SERVICE_KEY}"
    assert request.headers["apikey"] == SERVICE_KEY
    assert request.headers["content-type"] == "image/jpeg"
    assert request.headers["x-upsert"] == "false"
    assert request.content == b"\xff\xd8\xff photo"


def test_upload_rejected_by_storage_raises_a_storage_error() -> None:
    storage = _storage(lambda request: httpx.Response(400, json={"message": "Bucket not found"}))

    with pytest.raises(EvidenceStorageError):
        storage.upload(OBJECT_KEY, b"\x89PNG\r\n\x1a\n", "image/png")


def test_upload_network_failure_raises_a_storage_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(EvidenceStorageError):
        _storage(handler).upload(OBJECT_KEY, b"x", "image/png")


def test_signed_url_requests_the_ttl_and_returns_an_absolute_url() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"signedURL": f"/object/sign/{BUCKET}/{OBJECT_KEY}?token=t0k"})

    url = _storage(handler).create_signed_url(OBJECT_KEY, 300)

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/storage/v1/object/sign/{BUCKET}/{OBJECT_KEY}"
    assert request.headers["authorization"] == f"Bearer {SERVICE_KEY}"
    assert json.loads(request.content) == {"expiresIn": 300}
    assert url == f"{BASE_URL}/storage/v1/object/sign/{BUCKET}/{OBJECT_KEY}?token=t0k"


def test_signed_url_failure_raises_a_storage_error() -> None:
    storage = _storage(lambda request: httpx.Response(500, json={"message": "boom"}))

    with pytest.raises(EvidenceStorageError):
        storage.create_signed_url(OBJECT_KEY, 300)


def test_signed_url_response_without_a_url_raises_a_storage_error() -> None:
    storage = _storage(lambda request: httpx.Response(200, json={"unexpected": True}))

    with pytest.raises(EvidenceStorageError):
        storage.create_signed_url(OBJECT_KEY, 300)


def test_delete_removes_the_object_through_the_bulk_remove_endpoint() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[{"name": OBJECT_KEY}])

    _storage(handler).delete(OBJECT_KEY)

    request = seen[0]
    assert request.method == "DELETE"
    assert str(request.url) == f"{BASE_URL}/storage/v1/object/{BUCKET}"
    assert request.headers["authorization"] == f"Bearer {SERVICE_KEY}"
    assert json.loads(request.content) == {"prefixes": [OBJECT_KEY]}


def test_delete_rejected_by_storage_raises_a_storage_error() -> None:
    storage = _storage(lambda request: httpx.Response(500, json={"message": "boom"}))

    with pytest.raises(EvidenceStorageError):
        storage.delete(OBJECT_KEY)


def test_delete_network_failure_raises_a_storage_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with pytest.raises(EvidenceStorageError):
        _storage(handler).delete(OBJECT_KEY)
