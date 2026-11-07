"""Customer images attached to a service request: owner upload, capped count, signed reads for the visible provider."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.evidence_storage import EvidenceStorageError, get_request_image_storage_resolver
from amira_api.main import app
from amira_api.models import (
    FormularioServicio,
    ImagenFormulario,
    RolPerfil,
    RolUsuario,
    TipoServicio,
)
from amira_api.settings import Settings, get_settings
from chat_support import (  # noqa: F401
    CUSTOMER_AUTH,
    OTHER_CUSTOMER_AUTH,
    PROVIDER_AUTH,
    Scenario,
    _profile,
    _user,
    db,
    scenario,
)

OTHER_PROVIDER_AUTH = UUID("8b1d1f4e-0c3a-4a52-9d55-6f1d7a1c2e09")
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
HTML = b"<html><script>alert(1)</script></html>"
SIGNED_BASE = "https://storage.example.test"
MAX_BYTES = 5 * 1024 * 1024
MAX_IMAGES = 5
CONFIGURED = {
    "supabase_url": "https://project.example.test",
    "supabase_service_role_key": "service-role-test",
    "request_images_bucket": "request-images",
}


class FakeRequestImageStorage:
    def __init__(self) -> None:
        self.fail_upload = False
        # Runs at the start of every upload, to simulate other requests writing while this one is in storage.
        self.before_upload = None
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.signed: list[tuple[str, int]] = []

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        if self.before_upload is not None:
            self.before_upload()
        if self.fail_upload:
            raise EvidenceStorageError("storage unavailable")
        self.uploads[key] = (content, content_type)

    def delete(self, key: str) -> None:
        self.deleted.append(key)

    def create_signed_url(self, key: str, expires_in: int) -> str:
        self.signed.append((key, expires_in))
        return f"{SIGNED_BASE}/{key}?token=signed"


@dataclass
class RequestContext:
    request_id: UUID
    other_provider_profile_id: UUID
    scenario: Scenario


class RequestImageApi:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.settings = dict(CONFIGURED)

    def as_user(self, auth_id: UUID) -> None:
        app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
            id=auth_id,
            email="caller@example.test",
            session_id=uuid4(),
            assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )

    def configure(self, **overrides) -> None:
        self.settings = {**CONFIGURED, **overrides}
        app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **self.settings)

    def upload(self, request_id: UUID, *, as_auth_id: UUID, photo: bytes = JPEG, filename: str = "foto.jpg",
               content_type: str = "image/jpeg"):
        self.as_user(as_auth_id)
        return self.client.post(
            f"/api/requests/{request_id}/images",
            files={"photo": (filename, photo, content_type)},
        )

    def list_images(self, request_id: UUID, *, as_auth_id: UUID):
        self.as_user(as_auth_id)
        return self.client.get(f"/api/requests/{request_id}/images")


@pytest.fixture
def storage() -> FakeRequestImageStorage:
    return FakeRequestImageStorage()


@pytest.fixture
def api(db: Session, storage: FakeRequestImageStorage):
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_request_image_storage_resolver] = lambda: (lambda: storage)
    request_api = RequestImageApi(client=TestClient(app))
    request_api.configure()
    yield request_api
    for dependency in (get_db_session, get_current_user, get_request_image_storage_resolver, get_settings):
        app.dependency_overrides.pop(dependency, None)


@pytest.fixture
def request_context(db: Session, scenario: Scenario) -> RequestContext:
    """A pending request from the scenario customer to the scenario company profile, plus an unrelated provider.

    The provider detail rule reads the Rol_Usuario and Rol_Perfil codes, so the roles are seeded here.
    """
    bind = db.get_bind()
    # Regiones carries PostgreSQL-only regex CHECKs, so it is created as plain SQL, like Comunas in chat_support.
    with bind.begin() as connection:
        connection.execute(text(
            'CREATE TABLE IF NOT EXISTS "Regiones" ("Codigo" VARCHAR(2) PRIMARY KEY, "Nombre" VARCHAR(120) NOT NULL)'
        ))
    for model in (RolUsuario, RolPerfil, ImagenFormulario):
        model.__table__.create(bind=bind, checkfirst=True)
    client_role = RolUsuario(id=uuid4(), name="Cliente", code="client")
    owner_role = RolUsuario(id=uuid4(), name="Dueño empresa", code="company_owner")
    company_profile_role = RolPerfil(id=uuid4(), name="Empresa", code="company")
    db.add_all([client_role, owner_role, company_profile_role])
    db.flush()
    scenario.customer.role_id = client_role.id
    scenario.provider_owner.role_id = owner_role.id
    scenario.provider_profile.role_id = company_profile_role.id

    other_owner = _user(db, auth_id=OTHER_PROVIDER_AUTH, first="Olga", last="Otra", email="olga@example.test")
    other_owner.role_id = owner_role.id
    other_profile = _profile(db, owner=other_owner, name="Otra Logística", kind="company")
    other_profile.role_id = company_profile_role.id
    db.flush()

    mudanzas = db.query(TipoServicio).filter_by(slug="mudanzas").one()
    form = FormularioServicio(
        id=uuid4(),
        profile_id=scenario.provider_profile.id,
        service_type_id=mudanzas.id,
        origin="Santiago",
        destination="Valparaíso",
        status="pending",
        customer_id=scenario.customer.id,
        is_exclusive=False,
    )
    db.add(form)
    db.commit()
    return RequestContext(
        request_id=form.id,
        other_provider_profile_id=other_profile.id,
        scenario=scenario,
    )


def _images_in(db: Session, request_id: UUID) -> list[ImagenFormulario]:
    return db.query(ImagenFormulario).filter(ImagenFormulario.form_id == request_id).all()


def test_owner_uploads_an_image_and_the_row_and_object_are_stored(api, db: Session, request_context, storage):
    response = api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 201
    rows = _images_in(db, request_context.request_id)
    assert len(rows) == 1
    key = rows[0].private_storage_key
    assert key.startswith(f"requests/{request_context.request_id}/")
    assert key.endswith(".jpg")
    assert storage.uploads[key] == (JPEG, "image/jpeg")


def test_another_customer_is_refused_with_404_and_nothing_is_stored(api, db: Session, request_context, storage):
    response = api.upload(request_context.request_id, as_auth_id=OTHER_CUSTOMER_AUTH)

    assert response.status_code == 404
    assert _images_in(db, request_context.request_id) == []
    assert storage.uploads == {}


def test_a_provider_cannot_upload_to_a_request(api, db: Session, request_context, storage):
    response = api.upload(request_context.request_id, as_auth_id=PROVIDER_AUTH)

    assert response.status_code == 404
    assert _images_in(db, request_context.request_id) == []
    assert storage.uploads == {}


def test_a_non_image_with_an_image_extension_is_refused_with_415(api, db: Session, request_context, storage):
    response = api.upload(
        request_context.request_id, as_auth_id=CUSTOMER_AUTH, photo=HTML, filename="foto.jpg", content_type="image/jpeg"
    )

    assert response.status_code == 415
    assert _images_in(db, request_context.request_id) == []
    assert storage.uploads == {}


def test_an_image_over_the_chat_size_cap_is_refused_with_413(api, db: Session, request_context, storage):
    oversize = JPEG + b"\x00" * (MAX_BYTES + 1 - len(JPEG))

    response = api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH, photo=oversize)

    assert response.status_code == 413
    assert _images_in(db, request_context.request_id) == []
    assert storage.uploads == {}


def test_the_sixth_image_is_refused_with_409_and_no_upload(api, db: Session, request_context, storage):
    for _ in range(MAX_IMAGES):
        db.add(ImagenFormulario(id=uuid4(), form_id=request_context.request_id, private_storage_key=f"requests/x/{uuid4()}.jpg"))
    db.commit()

    response = api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH, photo=PNG, filename="foto.png",
                          content_type="image/png")

    assert response.status_code == 409
    assert len(_images_in(db, request_context.request_id)) == MAX_IMAGES
    assert storage.uploads == {}


def test_an_unset_bucket_fails_closed_with_503_and_writes_nothing(api, db: Session, request_context, storage):
    # The real resolver must run here, so the fake storage from the fixture is removed for this test only.
    app.dependency_overrides.pop(get_request_image_storage_resolver, None)
    api.configure(request_images_bucket=None)

    response = api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 503
    assert _images_in(db, request_context.request_id) == []
    assert storage.uploads == {}


def test_a_failed_storage_upload_answers_502_and_writes_no_row(api, db: Session, request_context, storage):
    storage.fail_upload = True

    response = api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 502
    assert _images_in(db, request_context.request_id) == []


def test_the_allowed_provider_reads_short_lived_signed_urls(api, db: Session, request_context, storage):
    api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    response = api.list_images(request_context.request_id, as_auth_id=PROVIDER_AUTH)

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    key = _images_in(db, request_context.request_id)[0].private_storage_key
    assert items[0]["url"] == f"{SIGNED_BASE}/{key}?token=signed"
    assert storage.signed == [(key, 300)]


def test_the_owner_customer_reads_the_signed_urls(api, db: Session, request_context, storage):
    api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    response = api.list_images(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1


def test_an_unrelated_provider_gets_the_same_response_as_the_detail_route(api, db: Session, request_context, storage):
    api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    response = api.list_images(request_context.request_id, as_auth_id=OTHER_PROVIDER_AUTH)
    detail = api.client.get(f"/api/provider/requests/{request_context.request_id}")

    assert response.status_code == detail.status_code == 404
    assert response.json() == detail.json()
    assert storage.signed == []


def test_the_provider_detail_route_still_serves_the_profile_owner(api, db: Session, request_context):
    api.as_user(PROVIDER_AUTH)

    response = api.client.get(f"/api/provider/requests/{request_context.request_id}")

    assert response.status_code == 200
    assert response.json()["requestId"] == str(request_context.request_id)


def test_concurrent_uploads_filling_the_limit_during_storage_answer_409_and_drop_the_object(api, db: Session, request_context, storage):
    request_id = request_context.request_id

    def other_uploads_fill_the_limit() -> None:
        for _ in range(MAX_IMAGES):
            db.add(ImagenFormulario(id=uuid4(), form_id=request_id, private_storage_key=f"requests/other/{uuid4()}.jpg"))
        db.commit()

    storage.before_upload = other_uploads_fill_the_limit

    response = api.upload(request_id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 409
    rows = _images_in(db, request_id)
    assert len(rows) == MAX_IMAGES
    assert all(row.private_storage_key.startswith("requests/other/") for row in rows)
    assert len(storage.deleted) == 1
    assert storage.deleted[0] in storage.uploads


def test_no_transaction_or_row_lock_is_open_while_the_object_is_uploaded(api, db: Session, request_context, storage):
    observed: list[bool] = []
    storage.before_upload = lambda: observed.append(db.in_transaction())

    response = api.upload(request_context.request_id, as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 201
    assert observed == [False]
