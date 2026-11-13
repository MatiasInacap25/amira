"""Manual review of driver certificates with annotations: list, approve and reject from the command line."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api import review_driver_verifications
from amira_api.driver_verification import is_driver_verified
from amira_api.driver_verification_review import ReviewRefused, approve_certificate, pending_reviews, reject_certificate
from amira_api.models import Base, RolUsuario, Usuario, VerificacionIdentidad
from chat_support import _register_btrim

NOW = datetime(2026, 11, 13, 12, tzinfo=UTC)


@pytest.fixture
def engine():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _register_btrim)
    Base.metadata.create_all(engine, tables=[Base.metadata.tables[name] for name in ("Rol_Usuario", "Usuario", "Verificacion_Identidad")])
    yield engine
    engine.dispose()


@pytest.fixture
def db(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture
def driver(db: Session) -> Usuario:
    role = RolUsuario(id=uuid4(), name="independent_driver", code="independent_driver")
    user = Usuario(id=uuid4(), auth_user_id=uuid4(), first_name="Pedro", last_name="Soto", email="pedro@example.test",
                   national_id="12345678-5", role_id=role.id)
    db.add_all([role, user])
    db.commit()
    return user


def certificate(db: Session, user: Usuario, document_type: str, status: str, folio: str) -> VerificacionIdentidad:
    row = VerificacionIdentidad(
        id=uuid4(), user_id=user.id, provider="verifik", provider_verification_id=folio, status=status,
        document_type=document_type, annotations=[{"register": "Registro General de Condenas", "fines": "Condena 2019"}],
        rejection_reason="El certificado tiene anotaciones y será revisado por el equipo de Amira." if status == "in_review" else None,
        verified_at=NOW if status == "verified" else None, created_at=NOW, updated_at=NOW,
    )
    db.add(row)
    db.commit()
    return row


def test_pending_reviews_list_only_certificates_in_review_with_their_holder(db, driver) -> None:
    pending = certificate(db, driver, "criminal_record", "in_review", "50070080801")
    certificate(db, driver, "driver_record", "verified", "50070080802")

    rows = pending_reviews(db)

    assert [(item.id, item.holder, item.rut, item.document_type, item.folio) for item in rows] == [
        (pending.id, "Pedro Soto", "12345678-5", "criminal_record", "50070080801"),
    ]
    assert rows[0].annotations == [{"register": "Registro General de Condenas", "fines": "Condena 2019"}]


def test_approving_a_certificate_in_review_verifies_it_and_completes_the_driver(db, driver) -> None:
    pending = certificate(db, driver, "criminal_record", "in_review", "50070080801")
    certificate(db, driver, "driver_record", "verified", "50070080802")

    approve_certificate(db, pending.id, NOW)

    db.refresh(pending)
    assert (pending.status, pending.rejection_reason) == ("verified", None)
    assert pending.verified_at is not None and pending.reviewed_at is not None
    assert is_driver_verified(db, driver.id)


def test_rejecting_a_certificate_in_review_stores_the_reason(db, driver) -> None:
    pending = certificate(db, driver, "criminal_record", "in_review", "50070080801")

    reject_certificate(db, pending.id, "  Condena incompatible con transporte de carga.  ", NOW)

    db.refresh(pending)
    assert (pending.status, pending.rejection_reason) == ("rejected", "Condena incompatible con transporte de carga.")
    assert pending.verified_at is None and pending.reviewed_at is not None


@pytest.mark.parametrize("status", ["verified", "rejected"])
def test_only_certificates_in_review_can_be_decided(db, driver, status) -> None:
    row = certificate(db, driver, "criminal_record", status, "50070080801")

    with pytest.raises(ReviewRefused):
        approve_certificate(db, row.id, NOW)
    with pytest.raises(ReviewRefused):
        reject_certificate(db, row.id, "motivo", NOW)
    db.refresh(row)
    assert row.status == status


def test_unknown_certificates_and_blank_reasons_are_refused(db, driver) -> None:
    pending = certificate(db, driver, "criminal_record", "in_review", "50070080801")

    with pytest.raises(ReviewRefused):
        approve_certificate(db, uuid4(), NOW)
    with pytest.raises(ReviewRefused):
        reject_certificate(db, pending.id, "   ", NOW)
    db.refresh(pending)
    assert pending.status == "in_review"


# Command line

def run(engine, monkeypatch, capsys, *argv: str) -> tuple[int, str, str]:
    monkeypatch.setattr(review_driver_verifications, "get_engine", lambda: engine)
    code = review_driver_verifications.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_lists_approves_and_rejects(engine, db, driver, monkeypatch, capsys) -> None:
    first = certificate(db, driver, "criminal_record", "in_review", "50070080801")
    second = certificate(db, driver, "driver_record", "in_review", "50070080802")
    first.pdf_storage_key = f"driver-certificates/{driver.id}/{first.id}.pdf"
    db.commit()

    code, out, _ = run(engine, monkeypatch, capsys, "list")
    assert code == 0
    assert str(first.id) in out and str(second.id) in out
    assert "Pedro Soto" in out and "Condena 2019" in out
    assert first.pdf_storage_key in out

    assert run(engine, monkeypatch, capsys, "approve", str(first.id))[0] == 0
    assert run(engine, monkeypatch, capsys, "reject", str(second.id), "--reason", "Infracción gravísima reciente")[0] == 0
    db.expire_all()
    assert (db.get(VerificacionIdentidad, first.id).status, db.get(VerificacionIdentidad, second.id).status) == ("verified", "rejected")


def test_cli_reports_an_empty_queue(engine, monkeypatch, capsys) -> None:
    code, out, _ = run(engine, monkeypatch, capsys, "list")
    assert code == 0
    assert "No hay certificados en revisión." in out


def test_cli_exits_2_when_a_decision_is_refused(engine, db, driver, monkeypatch, capsys) -> None:
    row = certificate(db, driver, "criminal_record", "verified", "50070080801")
    code, _, err = run(engine, monkeypatch, capsys, "approve", str(row.id))
    assert code == 2
    assert "no está en revisión" in err


def test_cli_exits_1_when_the_database_is_not_configured(monkeypatch, capsys) -> None:
    def missing():
        raise RuntimeError("DATABASE_URL is not configured.")

    monkeypatch.setattr(review_driver_verifications, "get_engine", missing)
    assert review_driver_verifications.main(["list"]) == 1


def test_cli_rejects_a_malformed_id(monkeypatch, capsys) -> None:
    with pytest.raises(SystemExit) as raised:
        review_driver_verifications.main(["approve", "not-a-uuid"])
    assert raised.value.code == 2
