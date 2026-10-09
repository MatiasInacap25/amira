from collections import deque
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy.exc import IntegrityError

from amira_api.account_routes import provision_account
from amira_api.account_schemas import AccountProvisionRequest
from amira_api.auth import AuthenticatedUser
from amira_api.models import Conductor, Perfil, RolPerfil, RolUsuario, TipoConductor, Usuario
from amira_api.settings import Settings


USER_ID = UUID("123e4567-e89b-12d3-a456-426614174000")
SESSION_ID = UUID("123e4567-e89b-12d3-a456-426614174001")
USER_ROLE_ID = UUID("b2000000-0000-4000-8000-000000000002")
PROFILE_ROLE_ID = UUID("b2000000-0000-4000-8000-000000000005")
DRIVER_TYPE_ID = UUID("b2000000-0000-4000-8000-000000000010")
PERSONAL_RUT = "12345678-5"
COMPANY_RUT = "76123456-0"
PHONE = "+56912345678"


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
    return AuthenticatedUser(
        id=USER_ID,
        email="person@example.test",
        session_id=SESSION_ID,
        assurance="aal2",
        authentication_methods=frozenset({"password"}),
    )


def role(code, role_id):
    return RolUsuario(id=role_id, code=code, name=code)


def profile_role(code, role_id):
    return RolPerfil(id=role_id, code=code, name=code)


def test_company_owner_provisioning_creates_profile_but_never_driver():
    company_role = role("company_owner", USER_ROLE_ID)
    profile_kind = profile_role("company", PROFILE_ROLE_ID)
    session = FakeSession([company_role, None, profile_kind, None, None])
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        display_name="Casey Logistics",
        company_tax_id=COMPANY_RUT,
    )

    http_response = Response()
    response = provision_account(payload, identity(), session, Settings(_env_file=None), http_response)

    assert response.role == "company_owner"
    assert response.profile_id is not None
    assert [type(item) for item in session.added] == [Usuario, Perfil]
    user, profile = session.added
    assert user.email == "person@example.test"  # request cannot choose the account email
    assert profile.kind == "company"
    assert profile.company_tax_id == COMPANY_RUT
    assert user.national_id == PERSONAL_RUT
    assert user.birth_date == date(1990, 1, 1)
    assert user.phone == PHONE
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
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        role_id=USER_ROLE_ID,
    )
    profile = Perfil(
        id=UUID("123e4567-e89b-12d3-a456-426614174011"),
        owner_user_id=user.id,
        name="Casey Logistics",
        role_id=PROFILE_ROLE_ID,
        kind="company",
        company_tax_id=COMPANY_RUT,
    )
    session = FakeSession([account_role, user, profile_kind, profile, None])
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        display_name="Casey Logistics",
        company_tax_id=COMPANY_RUT,
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
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        role_id=account_role.id,
    )

    class RacingSession(FakeSession):
        def flush(self):
            raise IntegrityError("insert", {}, Exception("unique constraint"))

    session = RacingSession([account_role, None, winner])
    payload = AccountProvisionRequest(role="client", first_name="Casey", last_name="Client", national_id=PERSONAL_RUT, birth_date=date(1990, 1, 1), phone=PHONE)
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
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
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
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        display_name="Casey Transport",
    )

    with pytest.raises(HTTPException) as error:
        provision_account(payload, identity(), session, Settings(_env_file=None), Response())

    assert error.value.status_code == 503
    assert not any(isinstance(item, Conductor) for item in session.added)


def test_role_specific_profile_fields_are_validated():
    with pytest.raises(ValueError):
        AccountProvisionRequest(role="client", first_name="Casey", last_name="Client", national_id=PERSONAL_RUT, birth_date=date(1990, 1, 1), phone=PHONE, display_name="Not allowed")
    with pytest.raises(ValueError):
        AccountProvisionRequest(role="company_owner", first_name="Casey", last_name="Owner", national_id=PERSONAL_RUT, birth_date=date(1990, 1, 1), phone=PHONE, display_name="No RUT")
    with pytest.raises(ValueError):
        AccountProvisionRequest(role="independent_driver", first_name="Casey", last_name="Driver", national_id=PERSONAL_RUT, birth_date=date(1990, 1, 1), phone=PHONE, display_name="Transport", company_tax_id=COMPANY_RUT)


def test_chilean_personal_and_company_ruts_are_validated_and_normalized():
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        national_id="12.345.678-5",
        birth_date=date(1990, 1, 1),
        phone="+56 (9) 1234-5678",
        display_name="Casey Logistics",
        company_tax_id="76.123.456-0",
    )
    assert payload.national_id == PERSONAL_RUT
    assert payload.company_tax_id == COMPANY_RUT
    assert payload.phone == PHONE

    with pytest.raises(ValueError):
        AccountProvisionRequest(role="client", first_name="Casey", last_name="Client", national_id="12.345.678-0", birth_date=date(1990, 1, 1), phone=PHONE)


@pytest.mark.parametrize(
    "overrides",
    [
        {"phone": "not-a-phone"},
        {"birth_date": date(2099, 1, 1)},
        {"birth_date": date(1899, 12, 31)},
        {"email": "untrusted@example.test"},
    ],
)
def test_private_account_input_is_validated_and_email_cannot_be_supplied(overrides):
    values = {
        "role": "client",
        "first_name": "Casey",
        "last_name": "Client",
        "national_id": PERSONAL_RUT,
        "birth_date": date(1990, 1, 1),
        "phone": PHONE,
    }
    values.update(overrides)
    with pytest.raises(ValueError):
        AccountProvisionRequest(**values)


def test_company_owner_can_opt_into_a_company_linked_driver_without_exposing_private_data():
    company_role = role("company_owner", USER_ROLE_ID)
    profile_kind = profile_role("company", PROFILE_ROLE_ID)
    company_driver_type_id = UUID("b2000000-0000-4000-8000-000000000020")
    company_driver_type = TipoConductor(id=company_driver_type_id, name="trusted configured type")
    session = FakeSession([company_driver_type, company_role, None, profile_kind, None, None])
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        display_name="Casey Logistics",
        company_tax_id=COMPANY_RUT,
        also_driver=True,
    )

    result = provision_account(payload, identity(), session, Settings(_env_file=None, company_driver_type_id=company_driver_type_id), Response())

    profile = next(item for item in session.added if isinstance(item, Perfil))
    user = next(item for item in session.added if isinstance(item, Usuario))
    driver = next(item for item in session.added if isinstance(item, Conductor))
    assert driver.user_id == user.id
    assert driver.employer_profile_id == profile.id == result.profile_id
    assert driver.driver_type_id == company_driver_type_id
    assert result.model_dump().keys() == {"user_id", "role", "profile_id"}
    assert PERSONAL_RUT not in result.model_dump_json()
    assert PHONE not in result.model_dump_json()


@pytest.mark.parametrize("configured_type", [None, UUID("b2000000-0000-4000-8000-000000000099")])
def test_company_driver_opt_in_fails_closed_when_trusted_mapping_missing_or_invalid(configured_type):
    session = FakeSession([None])
    payload = AccountProvisionRequest(
        role="company_owner",
        first_name="Casey",
        last_name="Owner",
        national_id=PERSONAL_RUT,
        birth_date=date(1990, 1, 1),
        phone=PHONE,
        display_name="Casey Logistics",
        company_tax_id=COMPANY_RUT,
        also_driver=True,
    )
    settings = Settings(_env_file=None, company_driver_type_id=configured_type)

    with pytest.raises(HTTPException) as error:
        provision_account(payload, identity(), session, settings, Response())

    assert error.value.status_code == 503
    assert session.added == []
    assert session.commits == 0


@pytest.mark.parametrize("role_name", ["client", "independent_driver"])
def test_non_company_roles_cannot_use_company_driver_toggle(role_name):
    with pytest.raises(ValueError):
        AccountProvisionRequest(
            role=role_name,
            first_name="Casey",
            last_name="Driver",
            national_id=PERSONAL_RUT,
            birth_date=date(1990, 1, 1),
            phone=PHONE,
            display_name="Casey Transport" if role_name == "independent_driver" else None,
            also_driver=True,
        )
