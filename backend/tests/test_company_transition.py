from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from amira_api.account_routes import transition_to_company
from amira_api.account_schemas import CompanyTransitionRequest
from amira_api.auth import AuthenticatedUser
from amira_api.models import Conductor
from amira_api.settings import Settings

OWNER_AUTH_ID = UUID("a6607c8d-9ea3-4166-8bf2-2333ae164d57")
OWNER_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
INDEPENDENT_ROLE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e33")
COMPANY_ROLE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e34")
OWNER_ACCOUNT_ROLE_ID = UUID("04db2a78-34fb-429e-a9c9-9fc5a9d10e35")
DRIVER_TYPE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e37")


class Result:
    def __init__(self, *, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def one_or_none(self):
        return self.row

    def scalar_one_or_none(self):
        return self.scalar


class Session:
    def __init__(self, results, *, fail_commit=False):
        self.results = iter(results)
        self.committed = False
        self.rolled_back = False
        self.fail_commit = fail_commit

    def execute(self, _statement):
        return next(self.results)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("database write failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def owner_auth():
    return AuthenticatedUser(
        id=OWNER_AUTH_ID, email="owner@example.test",
        session_id=UUID("ecbe55b7-105f-44a1-b887-dfeef13c19d5"),
        assurance="aal2", authentication_methods=frozenset({"password"}),
    )


def setup(owner_role="independent_driver", *, fail_commit=False):
    owner = SimpleNamespace(id=OWNER_ID, role_id=INDEPENDENT_ROLE_ID)
    profile = SimpleNamespace(
        id=PROFILE_ID, owner_user_id=OWNER_ID, role_id=INDEPENDENT_ROLE_ID,
        kind="independent_driver", company_tax_id=None,
    )
    owner_driver = Conductor(id=UUID("b1de600b-7f0a-4a9b-8a42-c3715a47b593"), user_id=OWNER_ID,
                             driver_type_id=DRIVER_TYPE_ID, employer_profile_id=None)
    results = [
        Result(row=(owner, owner_role)), Result(row=(profile, "independent_driver")),
        Result(scalar=owner_driver), Result(scalar=SimpleNamespace(id=COMPANY_ROLE_ID)),
        Result(scalar=SimpleNamespace(id=OWNER_ACCOUNT_ROLE_ID)),
    ]
    return Session(results, fail_commit=fail_commit), owner, profile, owner_driver


def test_transition_schema_rejects_any_invitee_user_id():
    with pytest.raises(ValueError):
        CompanyTransitionRequest(driver_user_id=UUID(int=1), company_tax_id="76.123.456-0")


def test_transition_converts_same_profile_and_owner_without_touching_an_invitee():
    session, owner, profile, owner_driver = setup()

    result = transition_to_company(
        CompanyTransitionRequest(company_tax_id="76.123.456-0"), owner_auth(), session,
    )

    assert result.user_id == OWNER_ID and result.profile_id == PROFILE_ID
    assert result.role == "company_owner"
    assert profile.id == PROFILE_ID and profile.owner_user_id == OWNER_ID
    assert profile.kind == "company" and profile.role_id == COMPANY_ROLE_ID
    assert profile.company_tax_id == "76123456-0"
    assert owner.role_id == OWNER_ACCOUNT_ROLE_ID
    assert owner_driver.employer_profile_id == PROFILE_ID
    assert session.committed


def test_non_owner_cannot_convert_profile():
    session, _, _, _ = setup("company_driver")

    with pytest.raises(HTTPException) as error:
        transition_to_company(CompanyTransitionRequest(company_tax_id="76.123.456-0"), owner_auth(), session)

    assert error.value.status_code == 403
    assert not session.committed


def test_failed_conversion_commit_rolls_back_all_profile_changes():
    session, _, profile, _ = setup(fail_commit=True)

    with pytest.raises(RuntimeError, match="database write failed"):
        transition_to_company(CompanyTransitionRequest(company_tax_id="76.123.456-0"), owner_auth(), session)

    assert profile.kind == "company"
    assert session.rolled_back
    assert not session.committed
