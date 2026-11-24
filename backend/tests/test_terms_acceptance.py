from datetime import date, datetime
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.dialects import postgresql
from starlette.requests import Request

from amira_api.account_routes import ClientRequestInfo, get_client_request_info, provision_account
from amira_api.account_schemas import AccountProvisionRequest
from amira_api.models import Base, RolUsuario, TermsAcceptance, Usuario
from amira_api.settings import Settings
from amira_api.terms import TERMS_VERSION
from test_account_provisioning import FakeSession, PERSONAL_RUT, PHONE, USER_ID, identity, role


TERMS_MESSAGE = "Debes aceptar los Términos y Condiciones vigentes."
MIGRATION_PATH = Path(__file__).parents[1] / "alembic" / "versions" / "20261123_0001_terms_acceptance.py"
CLIENT_ROLE_ID = UUID("b2000000-0000-4000-8000-000000000001")
ON_CONFLICT = 'ON CONFLICT ("ID_Usuario", "Version") DO NOTHING'


def client_payload(**overrides):
    values = {
        "role": "client",
        "first_name": "Casey",
        "last_name": "Client",
        "national_id": PERSONAL_RUT,
        "birth_date": date(1990, 1, 1),
        "phone": PHONE,
    }
    values.update(overrides)
    return AccountProvisionRequest(**values)


def request_with(headers=None, client=("203.0.113.7", 50000)):
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/account/provision",
            "headers": raw_headers,
            "client": client,
            "query_string": b"",
            "root_path": "",
        }
    )


def terms_insert(session):
    (statement,) = session.statements
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


def load_migration():
    spec = spec_from_file_location("terms_acceptance_migration", MIGRATION_PATH)
    migration = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(migration)
    return migration


@pytest.mark.parametrize(
    "version",
    [None, "", "2026-01-01", "x" * 50],
    ids=["missing", "empty", "outdated", "longer-than-20"],
)
def test_missing_empty_or_outdated_terms_version_is_rejected_before_any_write(version):
    payload = client_payload(accepted_terms_version=version)
    session = FakeSession([])  # any database read would raise IndexError

    with pytest.raises(HTTPException) as error:
        provision_account(payload, identity(), session, Settings(_env_file=None), Response(), ClientRequestInfo(None, None))

    assert error.value.status_code == 422
    assert error.value.detail == [
        {"loc": ["body", "accepted_terms_version"], "msg": TERMS_MESSAGE, "type": "value_error"}
    ]
    assert session.added == []
    assert session.statements == []
    assert session.commits == 0


def test_valid_terms_version_stores_one_acceptance_row_with_timestamp_and_user_agent():
    client_role = role("client", CLIENT_ROLE_ID)
    session = FakeSession([client_role, None])
    payload = client_payload(accepted_terms_version=TERMS_VERSION)
    http_response = Response()
    info = ClientRequestInfo(ip="203.0.113.7", user_agent="pytest-agent/1.0")

    response = provision_account(payload, identity(), session, Settings(_env_file=None), http_response, info)

    _, params = terms_insert(session)
    user = next(item for item in session.added if isinstance(item, Usuario))
    assert [type(item) for item in session.added] == [Usuario]
    assert params["ID_Usuario"] == user.id == response.user_id
    assert params["Version"] == TERMS_VERSION == "2026-11-23"
    assert isinstance(params["Fecha_Aceptacion"], datetime)
    assert params["Fecha_Aceptacion"].tzinfo is not None
    assert params["IP"] == "203.0.113.7"
    assert params["User_Agent"] == "pytest-agent/1.0"
    assert session.commits == 1
    assert http_response.status_code == 201


def test_repeated_provision_with_same_version_does_not_insert_a_duplicate_row():
    client_role = role("client", CLIENT_ROLE_ID)
    user = Usuario(
        id=UUID("123e4567-e89b-12d3-a456-426614174030"),
        auth_user_id=USER_ID,
        first_name="Casey",
        last_name="Client",
        email="person@example.test",
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        role_id=CLIENT_ROLE_ID,
    )
    session = FakeSession([client_role, user])
    payload = client_payload(accepted_terms_version=TERMS_VERSION)
    http_response = Response()

    response = provision_account(payload, identity(), session, Settings(_env_file=None), http_response, ClientRequestInfo(None, None))

    assert response.user_id == user.id
    assert session.added == []
    assert ON_CONFLICT in terms_insert(session)[0]  # the database absorbs the repeat; no duplicate row
    assert session.commits == 1
    assert http_response.status_code == 200


def test_existing_account_without_acceptance_gets_exactly_one_row():
    client_role = role("client", CLIENT_ROLE_ID)
    user = Usuario(
        id=UUID("123e4567-e89b-12d3-a456-426614174031"),
        auth_user_id=USER_ID,
        first_name="Casey",
        last_name="Client",
        email="person@example.test",
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        role_id=CLIENT_ROLE_ID,
    )
    session = FakeSession([client_role, user, None])
    payload = client_payload(accepted_terms_version=TERMS_VERSION)

    provision_account(payload, identity(), session, Settings(_env_file=None), Response(), ClientRequestInfo(None, None))

    _, params = terms_insert(session)
    assert params["ID_Usuario"] == user.id
    assert params["Version"] == TERMS_VERSION


def test_terms_insert_is_on_conflict_do_nothing_and_adds_no_lookup():
    session = FakeSession([role("client", CLIENT_ROLE_ID), None])

    provision_account(client_payload(accepted_terms_version=TERMS_VERSION), identity(), session, Settings(_env_file=None), Response(), ClientRequestInfo(None, None))

    assert ON_CONFLICT in terms_insert(session)[0]
    assert not session.values  # both queued account lookups consumed; the terms row needed no SELECT


def test_forwarded_for_first_value_wins_and_user_agent_is_truncated_to_512():
    request = request_with(
        {"x-forwarded-for": "198.51.100.4, 10.0.0.1", "user-agent": "a" * 600},
    )

    info = get_client_request_info(request)

    assert info.ip == "198.51.100.4"
    assert info.user_agent == "a" * 512


def test_client_host_is_used_without_forwarded_header_and_absent_headers_stay_null():
    info = get_client_request_info(request_with({}, client=("203.0.113.9", 1)))
    assert info.ip == "203.0.113.9"
    assert info.user_agent is None

    anonymous = get_client_request_info(request_with({}, client=None))
    assert anonymous.ip is None


def test_terms_acceptance_model_and_migration_follow_the_contract():
    table = TermsAcceptance.__table__
    assert table.name == "Aceptacion_Terminos"
    assert table.c["ID_Usuario"].foreign_keys
    fk = next(iter(table.c["ID_Usuario"].foreign_keys))
    assert fk.target_fullname == "Usuario.ID"
    assert fk.ondelete == "CASCADE"
    assert table.c["ID_Usuario"].index is True
    assert table.c["Version"].type.length == 20
    assert table.c["Version"].nullable is False
    assert table.c["Fecha_Aceptacion"].nullable is False
    assert table.c["IP"].type.length == 64 and table.c["IP"].nullable is True
    assert table.c["User_Agent"].type.length == 512 and table.c["User_Agent"].nullable is True
    unique_columns = [
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("ID_Usuario", "Version") in unique_columns
    assert "Aceptacion_Terminos" in Base.metadata.tables

    migration = load_migration()
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert migration.revision == "20261123_0001"
    assert migration.down_revision == "20261120_0001"
    assert migration.RLS_TABLES == ("Aceptacion_Terminos",)
    assert 'ALTER TABLE "Aceptacion_Terminos" ENABLE ROW LEVEL SECURITY' in source
    assert 'REVOKE ALL ON TABLE "Aceptacion_Terminos" FROM PUBLIC, anon, authenticated' in source
    assert "drop_table" in source
