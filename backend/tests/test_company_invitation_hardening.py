from pathlib import Path
import os
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException

from amira_api import invitation_routes
from amira_api.auth import AuthenticatedUser
from amira_api.models import DriverInvitation
from amira_api.invitation_routes import InvitationCreate, create_invitation
from amira_api.settings import Settings

ROOT = Path(__file__).parents[2]
PROFILE_ID = UUID("04db2a78-34fb-429e-ae9c-9fc5a9d10e32")
OWNER_ID = UUID("59f7cf6f-4d38-4c9c-96e7-62f354874d1d")
AUTH_ID = UUID("2a45e1d3-243f-4f24-8a4b-37c33f404e97")


class Result:
    def __init__(self, *, row=None, scalar=None):
        self.row = row
        self.scalar = scalar

    def one_or_none(self):
        return self.row

    def scalar_one(self):
        return self.scalar


class Session:
    def __init__(self, results):
        self.results = iter(results)
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return next(self.results)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for value in self.added:
            if isinstance(value, DriverInvitation) and value.id is None:
                value.id = PROFILE_ID
        return None

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def get_bind(self):
        return SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))


class Sender:
    def send_invitation(self, _email, _link):
        return True


def user():
    return AuthenticatedUser(
        id=AUTH_ID,
        email="owner@example.test",
        session_id=UUID("ecbe55b7-105f-44a1-b887-dfeef13c19d5"),
        assurance="aal2",
        authentication_methods=frozenset({"password", "phone"}),
    )


def test_clean_checkout_main_imports_without_untracked_fallback_router():
    archive = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT}", "archive", "HEAD"], cwd=ROOT, check=True, capture_output=True,
    ).stdout
    with tempfile.TemporaryDirectory(prefix="amira-clean-checkout-") as temp_dir:
        with tarfile.open(fileobj=BytesIO(archive)) as bundle:
            bundle.extractall(temp_dir, filter="data")
        backend = Path(temp_dir) / "backend"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env["PYTHONPATH"] = str(backend / "src")
        result = subprocess.run(
            [sys.executable, "-c", "from amira_api.main import app; assert '/api/driver-invitations/accept' in app.openapi()['paths']"],
            cwd=backend, env=env, capture_output=True, text=True,
        )
    assert result.returncode == 0, result.stderr


def test_independent_owner_can_issue_pending_invite_without_profile_conversion():
    owner = SimpleNamespace(id=OWNER_ID, role_id="independent-role")
    profile = SimpleNamespace(id=PROFILE_ID, kind="independent_driver", role_id="independent-role", company_tax_id=None)
    session = Session([Result(row=(owner, profile, "independent_driver", "independent_driver")), Result(scalar=0), Result()])

    create_invitation(
        InvitationCreate(email="driver@example.test", company_tax_id="76.123.456-0"),
        user(), session, Settings(_env_file=None, frontend_base_url="https://amira.example"), Sender(),
    )

    assert profile.kind == "independent_driver"
    assert profile.role_id == "independent-role"
    assert profile.company_tax_id == "76123456-0"
    assert owner.role_id == "independent-role"
    assert session.committed


def test_acceptance_rate_limit_denies_requests_after_five_per_window():
    session = Session([Result(), Result(), Result(scalar=5)])

    with pytest.raises(HTTPException) as error:
        invitation_routes._record_acceptance_attempt(session, user())

    assert error.value.status_code == 429
    assert not session.added
    assert not session.committed
    assert session.rolled_back
    assert len(session.statements) == 3


def test_rate_limit_attempt_rows_are_session_scoped_and_do_not_store_token_or_email():
    session = Session([Result(), Result(), Result(scalar=0)])

    invitation_routes._record_acceptance_attempt(session, user())

    attempt = session.added[0]
    assert attempt.auth_user_id == AUTH_ID
    assert attempt.auth_session_id == str(user().session_id)
    assert not hasattr(attempt, "email")
    assert not hasattr(attempt, "token")
    assert session.committed


def test_acceptance_attempt_storage_is_rls_protected_and_contains_no_invite_material():
    migration = ROOT / "backend" / "alembic" / "versions" / "20261003_0002_driver_invitation_attempts.py"
    source = migration.read_text(encoding="utf-8")

    assert 'ALTER TABLE public."DriverInvitationAttempt" ENABLE ROW LEVEL SECURITY' in source
    assert 'REVOKE ALL PRIVILEGES ON TABLE public."DriverInvitationAttempt" FROM PUBLIC' in source
    assert "target_email" not in source
    assert "token_hash" not in source
