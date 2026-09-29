from collections import deque
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.exc import IntegrityError

from amira_api.account_routes import provision_account
from amira_api.account_schemas import AccountProvisionRequest
from amira_api.auth import AuthenticatedUser
from amira_api.models import Conductor, Perfil, RolPerfil, RolUsuario, Usuario
from amira_api.settings import Settings


USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
SESSION_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
USER_ROLE_ID = UUID("b2000000-0000-4000-8000-000000000002")
PROFILE_ROLE_ID = UUID("b2000000-0000-4000-8000-000000000005")
DRIVER_TYPE_ID = UUID("b2000000-0000-4000-8000-000000000010")


class Result:
    def __init__(self, value=None):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class FakeSession:
    def __init__(self, values):
        self.values = deque(values)
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement):
        return Result(self.values.popleft())

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def identity():
    return AuthenticatedUser(id=USER_ID, email="person@example.test", session_id=str(SESSION_ID), assurance="aal2")


def role(code, role_id):
    return RolUsuario(id=role_id, code=code, name=code)


def profile_role(code, role_id):
    return RolPerfil(id=role_id, code=code, name=code)


def test_company_owner_provisioning_creates_profile_but_never_driver():
    company_role = role("company_owner", USER_ROLE_ID)
    profile_kind = profile_role("company", PROFILE_ROLE_ID)
    session = FakeSession([company_role, None, profile_kind, None])
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        display_name="Casey Logistics",
        company_tax_id="76.123.456-7",
    )

    http_response = Response()
    response = provision_account(payload, identity(), session, Settings(_env_file=None), http_response)

    assert response.role == "company_owner"
    assert response.profile_id is not None
    assert [type(item) for item in session.added] == [Usuario, Perfil]
    user, profile = session.added
    assert user.email == "person@example.test"  # request cannot choose the account email
    assert profile.kind == "company"
    assert profile.company_tax_id == "76.123.456-7"
    assert not any(isinstance(item, Conductor) for item in session.added)
    assert session.commits == 1
    assert http_response.status_code == 201


def test_repeated_company_owner_provisioning_is_idempotent():
    account_role = role("company_owner", USER_ROLE_ID)
    profile_kind = profile_role("company", PROFILE_ROLE_ID)
    user = Usuario(
        id=UUID("123e4567-e89b-12d3-a456-426614174010"),
        auth_user_id=USER_ID,
        first_name="Casey",
        last_name="Owner",
        email="person@example.test",
        role_id=USER_ROLE_ID,
    )
    profile = Perfil(
        id=UUID("123e4567-e89b-12d3-a456-426614174011"),
        owner_user_id=user.id,
        name="Casey Logistics",
        role_id=PROFILE_ROLE_ID,
        kind="company",
        company_tax_id="76.123.456-7",
    )
    session = FakeSession([account_role, user, profile_kind, profile])
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        display_name="Casey Logistics",
        company_tax_id="76.123.456-7",
    )

    http_response = Response()
    response = provision_account(payload, identity(), session, Settings(_env_file=None), http_response)

    assert response.user_id == user.id
    assert response.profile_id == profile.id
    assert session.added == []
    assert session.commits == 1
    assert http_response.status_code == 200


def test_concurrent_user_insert_conflict_resolves_to_existing_account():
    account_role = role("client", UUID("b2000000-0000-4000-8000-000000000001"))
    winner = Usuario(
        id=UUID("123e4567-e89b-12d3-a456-426614174020"),
        auth_user_id=USER_ID,
        first_name="Casey",
        last_name="Client",
        email="person@example.test",
        role_id=account_role.id,
    )

    class RacingSession(FakeSession):
        def flush(self):
            raise IntegrityError("insert", {}, Exception("unique constraint"))

    session = RacingSession([account_role, None, winner])
    payload = AccountProvisionRequest(role="client", first_name="Casey", last_name="Client")
    http_response = Response()

    response = provision_account(payload, identity(), session, Settings(_env_file=None), http_response)

    assert response.user_id == winner.id
    assert http_response.status_code == 200
    assert session.rollbacks == 1
    assert session.commits == 1


def test_unique_constraints_back_idempotent_user_profile_and_driver_records():
    assert Usuario.auth_user_id.property.columns[0].unique is True
    assert Perfil.owner_user_id.property.columns[0].unique is True
    assert any(constraint.name == "uq_conductor_user" for constraint in Conductor.__table__.constraints)


def test_independent_driver_gets_null_employer_and_explicit_configured_type():
    driver_type = DRIVER_TYPE_ID
    account_role = role("independent_driver", UUID("b2000000-0000-4000-8000-000000000004"))
    profile_kind = profile_role("independent_driver", UUID("b2000000-0000-4000-8000-000000000006"))
    session = FakeSession([account_role, None, profile_kind, None, None])
    payload = AccountProvisionRequest(
        role="independent_driver",
        first_name="Casey",
        last_name="Driver",
        display_name="Casey Transport",
    )

    response = provision_account(payload, identity(), session, Settings(_env_file=None, independent_driver_type_id=driver_type), Response())

    driver = next(item for item in session.added if isinstance(item, Conductor))
    assert response.role == "independent_driver"
    assert driver.employer_profile_id is None
    assert driver.driver_type_id == driver_type


def test_independent_driver_fails_closed_without_explicit_type_mapping():
    account_role = role("independent_driver", UUID("b2000000-0000-4000-8000-000000000004"))
    profile_kind = profile_role("independent_driver", UUID("b2000000-0000-4000-8000-000000000006"))
    session = FakeSession([account_role, None, profile_kind, None])
    payload = AccountProvisionRequest(
        role="independent_driver",
        first_name="Casey",
        last_name="Driver",
        display_name="Casey Transport",
    )

    with pytest.raises(HTTPException) as error:
        provision_account(payload, identity(), session, Settings(_env_file=None), Response())

    assert error.value.status_code == 503
    assert not any(isinstance(item, Conductor) for item in session.added)


def test_role_specific_profile_fields_are_validated():
    with pytest.raises(ValueError):
        AccountProvisionRequest(role="client", first_name="Casey", last_name="Client", display_name="Not allowed")
    with pytest.raises(ValueError):
        AccountProvisionRequest(role="company_owner", first_name="Casey", last_name="Owner", display_name="No RUT")
    with pytest.raises(ValueError):
        AccountProvisionRequest(role="independent_driver", first_name="Casey", last_name="Driver", display_name="Transport", company_tax_id="76.123.456-7")
