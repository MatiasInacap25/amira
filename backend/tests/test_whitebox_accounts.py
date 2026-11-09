"""Account readback, replay, validation, and insert-conflict boundaries."""

from datetime import date
from types import SimpleNamespace as NS
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from amira_api.account_routes import get_account, provision_account
from amira_api.account_schemas import AccountProvisionRequest
from amira_api.settings import Settings
from test_account_provisioning import FakeSession, identity, PERSONAL_RUT, COMPANY_RUT, PHONE


def values(role="client", **overrides):
    result = dict(role=role, first_name="Casey", last_name="Client", national_id=PERSONAL_RUT,
                  birth_date=date(1990, 1, 1), phone=PHONE)
    if role != "client":
        result.update(display_name="Casey Transport", commune_code="13101")
    if role == "company_owner":
        result["company_tax_id"] = COMPANY_RUT
    return {**result, **overrides}


def records(role="client"):
    payload = AccountProvisionRequest(**values(role))
    user = NS(id=uuid4(), role_id=uuid4(), email=identity().email,
              **{key: getattr(payload, key) for key in ("first_name", "last_name", "national_id", "birth_date", "phone")})
    profile = NS(id=uuid4(), kind="company" if role == "company_owner" else "independent_driver",
                 role_id=uuid4(), name=payload.display_name, company_tax_id=payload.company_tax_id, commune_code="13101")
    return payload, user, profile


@pytest.mark.parametrize("existing", [False, True])
def test_get_account_returns_provisioned_identity_or_404(existing):
    user = NS(id=uuid4())
    profile_id = uuid4()
    session = Mock()
    session.execute.side_effect = [NS(one_or_none=lambda: (user, "client") if existing else None),
                                   NS(scalar_one_or_none=lambda: profile_id)]
    if not existing:
        with pytest.raises(HTTPException) as caught:
            get_account(identity(), session)
        assert caught.value.status_code == 404
    else:
        response = get_account(identity(), session)
        assert (response.user_id, response.role, response.profile_id) == (user.id, "client", profile_id)
    session.commit.assert_not_called()


@pytest.mark.parametrize("field", ["first_name", "last_name", "email", "national_id", "birth_date", "phone"])
def test_existing_account_rejects_each_changed_private_field(field):
    payload, user, _ = records()
    setattr(user, field, date(1991, 1, 1) if field == "birth_date" else "different")
    session = FakeSession([NS(id=user.role_id), user])
    with pytest.raises(HTTPException) as caught:
        provision_account(payload, identity(), session, Settings(), Response())
    assert caught.value.status_code == 409
    assert session.commits == 0


def test_legacy_account_fills_missing_private_fields_once():
    payload, user, _ = records()
    user.national_id = user.birth_date = user.phone = None
    session = FakeSession([NS(id=user.role_id), user])
    response = Response()
    result = provision_account(payload, identity(), session, Settings(), response)
    assert (user.national_id, user.birth_date, user.phone) == (payload.national_id, payload.birth_date, payload.phone)
    assert result.user_id == user.id and response.status_code == 200 and session.commits == 1


def test_missing_account_role_refuses_before_writes():
    session = FakeSession([None])
    with pytest.raises(HTTPException) as caught:
        provision_account(AccountProvisionRequest(**values()), identity(), session, Settings(), Response())
    assert caught.value.status_code == 503
    assert not session.added and session.commits == 0


@pytest.mark.parametrize("field", [None, "role_id", "first_name", "last_name", "email", "national_id", "birth_date", "phone", "matching"])
def test_user_insert_race_checks_every_recovered_field(field):
    payload, winner, _ = records()
    role_id = winner.role_id
    if field not in {None, "matching"}:
        setattr(winner, field, uuid4() if field == "role_id" else date(1991, 1, 1) if field == "birth_date" else "different")
    session = FakeSession([NS(id=role_id), None, None if field is None else winner])
    session.flush = Mock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    if field == "matching":
        response = Response()
        assert provision_account(payload, identity(), session, Settings(), response).user_id == winner.id
        assert response.status_code == 200 and session.commits == 1
    else:
        with pytest.raises(HTTPException) as caught:
            provision_account(payload, identity(), session, Settings(), Response())
        assert caught.value.status_code == 409 and session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.parametrize("field", [None, "kind", "name", "company_tax_id", "role_id", "commune_code"])
def test_existing_profile_replay_checks_each_field(field):
    payload, user, profile = records("company_owner")
    role_id = profile.role_id
    if field:
        setattr(profile, field, uuid4() if field == "role_id" else "different")
    session = FakeSession(["13101", NS(id=user.role_id), user, NS(id=role_id), profile, None])
    if field:
        with pytest.raises(HTTPException) as caught:
            provision_account(payload, identity(), session, Settings(), Response())
        assert caught.value.status_code == 409 and session.commits == 0
    else:
        assert provision_account(payload, identity(), session, Settings(), Response()).profile_id == profile.id
        assert session.commits == 1


@pytest.mark.parametrize("field", [None, "kind", "name", "company_tax_id", "role_id", "matching"])
def test_profile_insert_race_is_validated(field):
    payload, user, winner = records("company_owner")
    role_id = winner.role_id
    if field not in {None, "matching"}:
        setattr(winner, field, uuid4() if field == "role_id" else "different")
    session = FakeSession(["13101", NS(id=user.role_id), user, NS(id=role_id), None,
                           None if field is None else winner, None])
    session.flush = Mock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    if field == "matching":
        assert provision_account(payload, identity(), session, Settings(), Response()).profile_id == winner.id
        assert session.commits == 1
    else:
        with pytest.raises(HTTPException) as caught:
            provision_account(payload, identity(), session, Settings(), Response())
        assert caught.value.status_code == 409 and session.commits == 0
    assert session.rollbacks == 1


@pytest.mark.parametrize("role", ["independent_driver", "company_owner"])
@pytest.mark.parametrize("race", [False, True])
@pytest.mark.parametrize("state", ["matching", "missing", "employer", "type"])
def test_driver_replay_and_race_states(role, race, state):
    payload, user, profile = records(role)
    if role == "company_owner":
        payload = AccountProvisionRequest(**values(role, also_driver=True))
    driver_type = NS(id=uuid4())
    driver = NS(employer_profile_id=profile.id if role == "company_owner" else None,
                driver_type_id=driver_type.id, commune_code=None)
    if state == "employer":
        driver.employer_profile_id = uuid4()
    elif state == "type":
        driver.driver_type_id = uuid4()
    prefix = [driver_type] if role == "company_owner" else []
    results = [*prefix, "13101", NS(id=user.role_id), user, NS(id=profile.role_id), profile]
    if race:
        results += [None, None if state == "missing" else driver]
    else:
        results += [None if state == "missing" else driver]
    session = FakeSession(results)
    if race:
        session.flush = Mock(side_effect=IntegrityError("insert", {}, Exception("unique")))
    settings = Settings(independent_driver_type_id=driver_type.id, company_driver_type_id=driver_type.id)
    if state in {"employer", "type"} or (race and state == "missing"):
        with pytest.raises(HTTPException) as caught:
            provision_account(payload, identity(), session, settings, Response())
        assert caught.value.status_code == 409 and session.commits == 0
    else:
        result = provision_account(payload, identity(), session, settings, Response())
        assert result.profile_id == profile.id and session.commits == 1
        if not race and state == "matching" and role == "independent_driver":
            assert driver.commune_code == "13101"
    assert session.rollbacks == int(race)


@pytest.mark.parametrize("overrides", [{"display_name": None}, {"company_tax_id": COMPANY_RUT}, {"also_driver": True}, {"national_id": "abc-12345"}])
def test_independent_schema_rejects_incompatible_capabilities(overrides):
    with pytest.raises(ValidationError):
        AccountProvisionRequest(**values("independent_driver", **overrides))


def test_existing_account_cannot_change_role():
    payload, user, _ = records()
    session = FakeSession([NS(id=uuid4()), user])
    with pytest.raises(HTTPException) as caught:
        provision_account(payload, identity(), session, Settings(), Response())
    assert caught.value.status_code == 409 and session.commits == 0


def test_profile_role_configuration_is_required():
    payload, user, _ = records("company_owner")
    session = FakeSession(["13101", NS(id=user.role_id), user, None])
    with pytest.raises(HTTPException) as caught:
        provision_account(payload, identity(), session, Settings(), Response())
    assert caught.value.status_code == 503 and session.commits == 0


def test_company_owner_cannot_silently_drop_linked_driver_capability():
    payload, user, profile = records("company_owner")
    session = FakeSession(["13101", NS(id=user.role_id), user, NS(id=profile.role_id), profile, NS(id=uuid4())])
    with pytest.raises(HTTPException) as caught:
        provision_account(payload, identity(), session, Settings(), Response())
    assert caught.value.status_code == 409 and session.commits == 0


def test_independent_replay_preserves_existing_commune():
    payload, user, profile = records("independent_driver")
    driver_type = uuid4()
    driver = NS(employer_profile_id=None, driver_type_id=driver_type, commune_code="13101")
    session = FakeSession(["13101", NS(id=user.role_id), user, NS(id=profile.role_id), profile, driver])
    assert provision_account(payload, identity(), session, Settings(independent_driver_type_id=driver_type), Response()).profile_id == profile.id
    assert driver.commune_code == "13101" and session.commits == 1
