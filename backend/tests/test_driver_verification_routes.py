"""Driver verification endpoints: submit a certificate by folio and code, see both certificates' status."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.driver_certificates import (
    CertificateInvalid,
    CertificateNotFound,
    CertificateRecord,
    CertificateRegister,
    VerifikUnavailable,
)
from amira_api.driver_verification_routes import (
    get_certificate_verifier_resolver,
    get_driver_certificate_storage_resolver,
)
from amira_api.evidence_storage import EvidenceStorageError
from amira_api.main import app
from amira_api.models import Base, Conductor, RolUsuario, Usuario, VerificacionIdentidad
from chat_support import _register_btrim

DRIVER_AUTH = UUID("5d1f0a22-0000-4000-8000-000000000001")
OTHER_DRIVER_AUTH = UUID("5d1f0a22-0000-4000-8000-000000000002")
CUSTOMER_AUTH = UUID("5d1f0a22-0000-4000-8000-000000000003")
DRIVER_RUT = "12345678-5"
OTHER_RUT = "11111111-1"
CLEAN = "No registra anotaciones"
PDF = b"%PDF-1.7\n" + b"0" * 16
URL = "/api/driver/verifications"


class FakeVerifier:
    name = "verifik"

    def __init__(self) -> None:
        self.returns_pdf = True
        self.calls: list[tuple[str, str]] = []
        self.hints: list[tuple[str | None, str | None]] = []
        self.results: dict[str, CertificateRecord | Exception] = {}

    def verify_certificate(self, folio: str, verification_code: str, *, holder_run: str | None = None,
                           document_type: str | None = None) -> CertificateRecord:
        self.calls.append((folio, verification_code))
        self.hints.append((holder_run, document_type))
        result = self.results.get(folio)
        if result is None:
            raise CertificateNotFound("missing")
        if isinstance(result, Exception):
            raise result
        return result


class FakeStorage:
    def __init__(self) -> None:
        self.fail_upload = False
        self.fail_delete = False
        self.uploads: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise EvidenceStorageError("down")
        self.uploads[key] = (content, content_type)

    def delete(self, key: str) -> None:
        self.deleted.append(key)
        if self.fail_delete:
            raise EvidenceStorageError("down")

    def create_signed_url(self, key: str, expires_in: int) -> str:
        return f"https://storage.test/{key}"


def certificate(run: str = DRIVER_RUT, fines: str = CLEAN, pdf: bytes | None = PDF) -> CertificateRecord:
    return CertificateRecord(
        name="PEDRO SOTO",
        run=run,
        registers=(
            CertificateRegister(register="Registro General de Condenas", run=run, fines=CLEAN),
            CertificateRegister(register="Registro Especial de Condenas por Actos de Violencia Intrafamiliar", run=run, fines=fines),
        ),
        pdf=pdf,
    )


def driver_record(run: str = DRIVER_RUT) -> CertificateRecord:
    return CertificateRecord(
        name="PEDRO SOTO",
        run=run,
        registers=(CertificateRegister(register="Registro Nacional de Conductores de Vehículos Motorizados", run=run, fines=CLEAN),),
        pdf=PDF,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    tables = ("Rol_Usuario", "Usuario", "Conductor", "Verificacion_Identidad")
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in tables])
    with Session(engine) as session:
        roles = {code: RolUsuario(id=uuid4(), name=code, code=code) for code in ("client", "independent_driver", "company_driver")}
        session.add_all(roles.values())
        users = [
            (DRIVER_AUTH, DRIVER_RUT, "independent_driver", True),
            (OTHER_DRIVER_AUTH, OTHER_RUT, "company_driver", True),
            (CUSTOMER_AUTH, "22222222-2", "client", False),
        ]
        for auth_id, rut, role, is_driver in users:
            user = Usuario(id=uuid4(), auth_user_id=auth_id, first_name="Pat", last_name="Test", email=f"{auth_id}@example.test",
                           national_id=rut, role_id=roles[role].id)
            session.add(user)
            session.flush()
            if is_driver:
                session.add(Conductor(id=uuid4(), user_id=user.id, employer_profile_id=None, driver_type_id=uuid4()))
        session.commit()
        yield session
    engine.dispose()


@pytest.fixture
def verifier() -> FakeVerifier:
    return FakeVerifier()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def client(db, verifier, storage):
    app.dependency_overrides[get_db_session] = lambda: db
    app.dependency_overrides[get_certificate_verifier_resolver] = lambda: (lambda: verifier)
    app.dependency_overrides[get_driver_certificate_storage_resolver] = lambda: (lambda: storage)
    yield TestClient(app)
    app.dependency_overrides.clear()


def as_user(auth_id: UUID) -> None:
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=auth_id, email="caller@example.test", session_id=uuid4(), assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
    )


def submit(client: TestClient, kind: str = "criminal_record", folio: str = "50070080804", code: str = "2aacbb9a636a"):
    return client.post(URL, json={"type": kind, "folio": folio, "verification_code": code})


def rows(db: Session) -> list[VerificacionIdentidad]:
    db.expire_all()
    return list(db.execute(select(VerificacionIdentidad).order_by(VerificacionIdentidad.created_at)).scalars())


def test_a_driver_without_certificates_sees_both_missing(client) -> None:
    as_user(DRIVER_AUTH)
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json() == {
        "verified": False,
        "certificates": [
            {"type": "criminal_record", "status": "missing", "reason": None, "submitted_at": None, "verified_at": None},
            {"type": "driver_record", "status": "missing", "reason": None, "submitted_at": None, "verified_at": None},
        ],
    }


def test_a_clean_certificate_of_the_driver_is_verified_and_its_pdf_stored(client, db, verifier, storage) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate()

    response = submit(client)

    assert response.status_code == 201
    body = response.json()
    assert body["verified"] is False  # the second certificate is still missing
    assert body["certificates"][0]["status"] == "verified"
    assert body["certificates"][0]["verified_at"] is not None
    assert verifier.calls == [("50070080804", "2aacbb9a636a")]
    [row] = rows(db)
    assert (row.provider, row.provider_verification_id, row.document_type, row.status) == ("verifik", "50070080804", "criminal_record", "verified")
    assert row.pdf_storage_key in storage.uploads
    assert storage.uploads[row.pdf_storage_key] == (PDF, "application/pdf")
    assert row.annotations == [
        {"register": "Registro General de Condenas", "fines": CLEAN},
        {"register": "Registro Especial de Condenas por Actos de Violencia Intrafamiliar", "fines": CLEAN},
    ]


def test_both_clean_certificates_verify_the_driver(client, verifier) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate()
    verifier.results["50070080805"] = driver_record()
    assert submit(client).status_code == 201

    response = submit(client, kind="driver_record", folio="50070080805")

    assert response.json()["verified"] is True
    assert [item["status"] for item in response.json()["certificates"]] == ["verified", "verified"]


def test_a_second_antecedentes_certificate_cannot_stand_in_for_the_driver_record(client, db, verifier) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate()
    verifier.results["50070080805"] = certificate()
    assert submit(client).status_code == 201

    response = submit(client, kind="driver_record", folio="50070080805")

    assert response.status_code == 201
    assert response.json()["verified"] is False
    assert response.json()["certificates"][1]["status"] == "in_review"
    assert rows(db)[1].document_type == "driver_record"


def test_annotations_leave_the_certificate_in_review(client, db, verifier) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate(fines="Infracción gravísima 2024")

    response = submit(client)

    assert response.status_code == 201
    assert response.json()["certificates"][0]["status"] == "in_review"
    assert response.json()["certificates"][0]["reason"] == "El certificado tiene anotaciones y será revisado por el equipo de Amira."
    assert rows(db)[0].verified_at is None


def test_another_persons_certificate_is_rejected_and_can_be_replaced(client, db, verifier) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate(run=OTHER_RUT)
    verifier.results["50070080806"] = certificate()

    rejected = submit(client)
    assert rejected.status_code == 201
    assert rejected.json()["certificates"][0] == {
        "type": "criminal_record", "status": "rejected", "reason": "El certificado pertenece a otra persona.",
        "submitted_at": rejected.json()["certificates"][0]["submitted_at"], "verified_at": None,
    }

    retried = submit(client, folio="50070080806")
    assert retried.json()["certificates"][0]["status"] == "verified"
    assert [row.status for row in rows(db)] == ["rejected", "verified"]


@pytest.mark.parametrize("status", ["verified", "in_review"])
def test_a_verified_or_pending_certificate_cannot_be_resubmitted(client, db, verifier, status) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate(fines=CLEAN if status == "verified" else "Anotación")
    verifier.results["50070080807"] = certificate()
    assert submit(client).status_code == 201

    response = submit(client, folio="50070080807")

    assert response.status_code == 409
    assert len(rows(db)) == 1
    assert verifier.calls == [("50070080804", "2aacbb9a636a")]


def test_a_folio_used_by_another_user_is_refused_without_calling_verifik(client, db, verifier) -> None:
    verifier.results["50070080804"] = certificate(run=OTHER_RUT)
    as_user(OTHER_DRIVER_AUTH)
    assert submit(client).status_code == 201

    as_user(DRIVER_AUTH)
    response = submit(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Este certificado ya fue usado en Amira."
    assert len(verifier.calls) == 1
    assert len(rows(db)) == 1


def test_a_certificate_verifik_does_not_find_is_a_422_and_stores_nothing(client, db) -> None:
    as_user(DRIVER_AUTH)
    response = submit(client, folio="9004040100001")
    assert response.status_code == 422
    assert response.json()["detail"] == "No encontramos un certificado con ese folio y código verificador."
    assert rows(db) == []


def test_malformed_input_rejected_by_verifik_is_a_422(client, db, verifier) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = CertificateInvalid("bad")
    assert submit(client).status_code == 422
    assert rows(db) == []


def test_verifik_failures_are_a_503_and_store_nothing(client, db, verifier, storage) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = VerifikUnavailable("down")
    response = submit(client)
    assert response.status_code == 503
    assert rows(db) == []
    assert storage.uploads == {}


def test_a_pdf_that_cannot_be_stored_is_a_503_and_stores_nothing(client, db, verifier, storage) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate()
    storage.fail_upload = True
    assert submit(client).status_code == 503
    assert rows(db) == []


def test_a_certificate_without_pdf_is_stored_without_a_key(client, db, verifier, storage) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate(pdf=None)
    assert submit(client).status_code == 201
    assert rows(db)[0].pdf_storage_key is None
    assert storage.uploads == {}


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "criminal_record", "folio": "123", "verification_code": "abc"},
        {"type": "criminal_record", "folio": "5007008080412345", "verification_code": "abc"},
        {"type": "criminal_record", "folio": "50070080804", "verification_code": ""},
        {"type": "criminal_record", "folio": "50070080804", "verification_code": "has space"},
        {"type": "passport", "folio": "50070080804", "verification_code": "abc"},
        {"type": "criminal_record", "folio": "50070080804", "verification_code": "abc", "extra": 1},
    ],
)
def test_invalid_payloads_are_rejected_before_calling_verifik(client, verifier, payload) -> None:
    as_user(DRIVER_AUTH)
    assert client.post(URL, json=payload).status_code == 422
    assert verifier.calls == []


def test_a_submission_stored_while_verifik_answered_wins_and_the_pdf_is_discarded(client, db, verifier, storage) -> None:
    as_user(DRIVER_AUTH)
    driver_id = db.execute(select(Usuario.id).where(Usuario.auth_user_id == DRIVER_AUTH)).scalar_one()
    original = verifier.verify_certificate

    def concurrent(folio: str, code: str, **hints) -> CertificateRecord:
        db.add(VerificacionIdentidad(id=uuid4(), user_id=driver_id, provider="verifik", provider_verification_id="50070080899",
                                     status="verified", document_type="criminal_record", created_at=datetime.now(UTC),
                                     updated_at=datetime.now(UTC)))
        db.commit()
        return original(folio, code, **hints)

    verifier.verify_certificate = concurrent
    verifier.results["50070080804"] = certificate()
    storage.fail_delete = True  # a failed cleanup is logged, never raised

    response = submit(client)

    assert response.status_code == 409
    assert [row.provider_verification_id for row in rows(db)] == ["50070080899"]
    assert storage.deleted == list(storage.uploads)


def test_a_folio_stored_concurrently_by_another_user_is_a_409(client, db, verifier, storage, monkeypatch) -> None:
    import amira_api.driver_verification_routes as routes

    other_id = db.execute(select(Usuario.id).where(Usuario.auth_user_id == OTHER_DRIVER_AUTH)).scalar_one()
    db.add(VerificacionIdentidad(id=uuid4(), user_id=other_id, provider="verifik", provider_verification_id="50070080804",
                                 status="verified", document_type="criminal_record", created_at=datetime.now(UTC),
                                 updated_at=datetime.now(UTC)))
    db.commit()
    monkeypatch.setattr(routes, "_ensure_folio_unused", lambda *_: None)
    as_user(DRIVER_AUTH)
    verifier.results["50070080804"] = certificate()

    response = submit(client)

    assert response.status_code == 409
    assert response.json()["detail"] == "Este certificado ya fue usado en Amira."
    assert storage.deleted == list(storage.uploads)


def test_certificate_storage_needs_supabase_and_a_bucket() -> None:
    from amira_api.driver_verification_routes import get_driver_certificate_storage_resolver
    from amira_api.settings import Settings
    from amira_api.supabase_evidence_storage import SupabaseEvidenceStorage

    unconfigured = get_driver_certificate_storage_resolver(Settings.model_construct())
    with pytest.raises(HTTPException) as raised:
        unconfigured()
    assert raised.value.status_code == 503

    configured = get_driver_certificate_storage_resolver(Settings.model_construct(
        supabase_url="https://project.example.test",
        supabase_service_role_key=SecretStr("service-role"),
        driver_certificates_bucket="driver-certificates",
    ))
    assert isinstance(configured(), SupabaseEvidenceStorage)


def test_the_verifier_resolver_builds_from_settings() -> None:
    from amira_api.settings import Settings
    from amira_api.simulated_certificate_verifier import SimulatedCertificateVerifier

    resolve = get_certificate_verifier_resolver(Settings.model_construct(verifik_simulator=True, app_env="test"))
    assert isinstance(resolve(), SimulatedCertificateVerifier)


def test_users_who_are_not_drivers_cannot_verify(client, verifier) -> None:
    as_user(CUSTOMER_AUTH)
    assert client.get(URL).status_code == 403
    assert submit(client).status_code == 403
    assert verifier.calls == []


def test_unknown_users_cannot_verify(client) -> None:
    as_user(uuid4())
    assert client.get(URL).status_code == 403


def test_the_verifier_receives_the_drivers_rut_and_the_declared_type(client, verifier) -> None:
    as_user(DRIVER_AUTH)
    verifier.results["50070080805"] = driver_record()

    assert submit(client, kind="driver_record", folio="50070080805").status_code == 201

    assert verifier.hints == [(DRIVER_RUT, "driver_record")]
