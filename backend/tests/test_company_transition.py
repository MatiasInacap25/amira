from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from amira_api.account_routes import transition_to_company
from amira_api.account_schemas import CompanyTransitionRequest
from amira_api.auth import AuthenticatedUser
from amira_api.models import Conductor
from amira_api.settings import Settings
from sqlalchemy.dialects import postgresql

OWNER_AUTH_ID = UUID("a6607c8d-9ea3-4166-8bf2-2333ae164d57")
OWNER_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
DRIVER_ID = UUID("2a45e1d3-243f-4f24-8a4b-37c33f404e97")
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
INDEPENDENT_ROLE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e33")
COMPANY_ROLE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e34")
OWNER_ACCOUNT_ROLE_ID = UUID("04db2a78-34fb-429e-a9c9-9fc5a9d10e35")
DRIVER_ACCOUNT_ROLE_ID = UUID("04db2a78-34fb-429e-a9c9-9fc5a9d10e36")
DRIVER_TYPE_ID = UUID("04db2a78-34fb-429e-a9c9-9fc5a9d10e37")


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
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.fail_commit = fail_commit
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("database write failed")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def owner_auth():
    return AuthenticatedUser(
        id=OWNER_AUTH_ID,
        email="owner@example.test",
        session_id=UUID("ecbe55b7-105f-44a1-b887-dfeef13c19d5"),
        assurance="aal2",
        authentication_methods=frozenset({"password"}),
    )


def seeded_results(owner_role="independent_driver", driver_role="client", *, driver_employer=None, already_company=False):
    owner = SimpleNamespace(id=OWNER_ID, role_id=OWNER_ACCOUNT_ROLE_ID if already_company else INDEPENDENT_ROLE_ID)
    profile = SimpleNamespace(
        id=PROFILE_ID,
        owner_user_id=OWNER_ID,
        role_id=COMPANY_ROLE_ID if already_company else INDEPENDENT_ROLE_ID,
        kind="company" if already_company else "independent_driver",
        company_tax_id="76123456-0" if already_company else None,
    )
    owner_driver = Conductor(id=UUID("b1de600b-7f0a-4a9b-8a42-c3715a47b593"), user_id=OWNER_ID, driver_type_id=DRIVER_TYPE_ID,
                             employer_profile_id=PROFILE_ID if already_company else None)
    driver_user = SimpleNamespace(id=DRIVER_ID, role_id=DRIVER_ACCOUNT_ROLE_ID if driver_role == "company_driver" else UUID("6633368a-3f77-4569-b203-57a1622d5851"))
    driver = None if driver_employer is None and not already_company else Conductor(
        id=UUID("629dd985-b7a2-4f9f-8aa7-925ed7812208"),
        user_id=DRIVER_ID,
        employer_profile_id=PROFILE_ID if already_company else driver_employer,
        driver_type_id=DRIVER_TYPE_ID,
    )
    results = [
        Result(row=(owner, "company_owner" if already_company else owner_role)),
        Result(row=(profile, profile.kind)),
        Result(scalar=owner_driver),
        Result(scalar=SimpleNamespace(id=COMPANY_ROLE_ID)),
        Result(scalar=SimpleNamespace(id=OWNER_ACCOUNT_ROLE_ID)),
        Result(scalar=SimpleNamespace(id=DRIVER_ACCOUNT_ROLE_ID)),
        Result(scalar=SimpleNamespace(id=DRIVER_TYPE_ID)),
        Result(row=(driver_user, driver_role)),
        Result(scalar=None),
        Result(scalar=driver),
    ]
    return results, {"owner": owner, "profile": profile, "owner_driver": owner_driver, "driver_user": driver_user}


def test_transition_preserves_profile_and_owner_and_links_existing_and_new_drivers():
    results, records = seeded_results()
    session = Session(results)
    result = transition_to_company(
        CompanyTransitionRequest(driver_user_id=DRIVER_ID, company_tax_id="76.123.456-0"),
        owner_auth(),
        session,
        Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
    )

    assert result.profile_id == PROFILE_ID
    assert result.role == "company_owner"
    assert records["profile"].id == PROFILE_ID
    assert records["profile"].owner_user_id == OWNER_ID
    assert records["profile"].kind == "company"
    assert records["profile"].company_tax_id == "76123456-0"
    assert records["profile"].role_id == COMPANY_ROLE_ID
    assert records["owner"].role_id == OWNER_ACCOUNT_ROLE_ID
    assert records["owner_driver"].employer_profile_id == PROFILE_ID
    assert records["driver_user"].role_id == DRIVER_ACCOUNT_ROLE_ID
    assert session.committed
    assert any(isinstance(value, Conductor) and value.user_id == DRIVER_ID and value.employer_profile_id == PROFILE_ID for value in session.added)


def test_company_driver_cannot_initiate_an_owner_transition():
    session = Session([Result(row=(SimpleNamespace(id=OWNER_ID), "company_driver"))])

    with pytest.raises(HTTPException) as error:
        transition_to_company(
            CompanyTransitionRequest(driver_user_id=DRIVER_ID, company_tax_id="76.123.456-0"),
            owner_auth(),
            session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
        )

    assert error.value.status_code == 403
    assert not session.committed


def test_transition_rejects_a_driver_already_linked_to_another_profile():
    results, _ = seeded_results(driver_employer=UUID("bdc7dd04-7a88-49da-8dd9-b4815c144c61"))
    session = Session(results)

    with pytest.raises(HTTPException) as error:
        transition_to_company(
            CompanyTransitionRequest(driver_user_id=DRIVER_ID, company_tax_id="76.123.456-0"),
            owner_auth(),
            session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
        )

    assert error.value.status_code == 409
    assert not session.committed
    assert session.added == []


def test_replayed_company_driver_transition_is_idempotent_and_uses_row_locks():
    results, records = seeded_results(driver_role="company_driver", already_company=True)
    session = Session(results)

    result = transition_to_company(
        CompanyTransitionRequest(driver_user_id=DRIVER_ID, company_tax_id="76.123.456-0"),
        owner_auth(),
        session,
        Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
    )

    assert result.profile_id == PROFILE_ID
    assert records["profile"].id == PROFILE_ID
    assert records["owner_driver"].employer_profile_id == PROFILE_ID
    assert session.added == []
    assert session.committed
    locked = [str(statement.compile(dialect=postgresql.dialect())) for statement in session.statements]
    assert sum("FOR UPDATE" in query for query in locked) == 5


def test_failed_commit_rolls_back_the_complete_transition():
    results, records = seeded_results()
    session = Session(results, fail_commit=True)

    with pytest.raises(RuntimeError, match="database write failed"):
        transition_to_company(
            CompanyTransitionRequest(driver_user_id=DRIVER_ID, company_tax_id="76.123.456-0"),
            owner_auth(),
            session,
            Settings(_env_file=None, company_driver_type_id=DRIVER_TYPE_ID),
        )

    assert records["profile"].kind == "company"
    assert session.rolled_back
    assert not session.committed
