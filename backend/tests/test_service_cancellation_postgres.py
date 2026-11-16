"""Opt-in PostgreSQL cancellation proofs isolated in unique, disposable schemas.

Only AMIRA_TEST_DATABASE_URL is accepted through the existing localhost guard.
No existing schema/table is changed; every test removes only its generated schema.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from decimal import Decimal
import importlib.util
from pathlib import Path
import time
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import (
    Base, Chat, Cotizacion, FormularioServicio, Pago, Perfil, Reembolso,
    RolPerfil, RolUsuario, Servicio, TipoServicio, Usuario,
)
from postgres_support import disposable_test_database_url, disposable_test_engine
from test_provider_service_actions import CUSTOMER_AUTH, OWNER_AUTH


@pytest.fixture
def isolated_postgres():
    url = disposable_test_database_url()
    administration = disposable_test_engine(url)
    schema = f"cancellation_test_{uuid4().hex}"
    engine = None
    with administration.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        engine = disposable_test_engine(url)

        @event.listens_for(engine, "connect")
        def isolate_connection(connection, _record):
            previous = connection.autocommit
            connection.autocommit = True
            with connection.cursor() as cursor:
                # Generated identifiers are restricted to ASCII letters, digits and underscores.
                cursor.execute(f'SET search_path TO "{schema}"')
                cursor.execute(f"SET application_name TO '{schema}'")
                cursor.execute("SET statement_timeout TO '10s'")
            connection.autocommit = previous

        yield engine, schema
    finally:
        if engine is not None:
            engine.dispose()
        with administration.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        administration.dispose()


def migration():
    path = Path(__file__).parents[1] / "alembic/versions/20261116_0001_service_cancellation.py"
    spec = importlib.util.spec_from_file_location("cancellation_postgres_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_postgres_migration_preserves_rows_and_refuses_lossy_downgrade(isolated_postgres):
    engine, schema = isolated_postgres
    module = migration()
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Servicio" ("ID" integer PRIMARY KEY, "Estado" text '
            'CONSTRAINT ck_service_status_allowed CHECK '
            '("Estado" IN (\'confirmed\', \'in_progress\', \'completed\', \'disputed\')))'
        ))
        connection.execute(text(
            'INSERT INTO "Servicio" VALUES '
            '(1, \'confirmed\'), (2, \'in_progress\'), (3, \'completed\'), (4, \'disputed\')'
        ))
        before = connection.execute(text('SELECT * FROM "Servicio" ORDER BY "ID"')).all()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert connection.execute(text('SELECT "ID", "Estado" FROM "Servicio" ORDER BY "ID"')).all() == before
        module.downgrade()
        assert connection.execute(text('SELECT * FROM "Servicio" ORDER BY "ID"')).all() == before
        module.upgrade()
        connection.execute(text('UPDATE "Servicio" SET "Estado" = \'cancelled\' WHERE "ID" = 1'))

    with pytest.raises(DBAPIError, match="Cannot downgrade while cancelled services exist"):
        with engine.begin() as connection:
            module.op = Operations(MigrationContext.configure(connection))
            module.downgrade()

    with engine.connect() as connection:
        assert connection.execute(text('SELECT "Estado" FROM "Servicio" WHERE "ID" = 1')).scalar_one() == "cancelled"
        columns = connection.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = :schema AND table_name = 'Servicio'"
        ), {"schema": schema}).scalars().all()
        assert set(columns) == {
            "ID", "Estado", "Fecha_Cancelacion", "Cancelado_Por",
            "Monto_Devuelto_Cancelacion", "Monto_Retenido_Cancelacion",
        }


def seed_services(engine):
    """Create valid local rows without disabling foreign keys or relying on public tables."""
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        client_role = RolUsuario(id=uuid4(), name="Client", code="client")
        owner_role = RolUsuario(id=uuid4(), name="Owner", code="company_owner")
        profile_role = RolPerfil(id=uuid4(), name="Company", code="company")
        service_type = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
        session.add_all([client_role, owner_role, profile_role, service_type])
        session.flush()
        customer = Usuario(
            id=uuid4(), auth_user_id=CUSTOMER_AUTH, first_name="Client", last_name="Test",
            email="client@example.test", role_id=client_role.id,
        )
        owner = Usuario(
            id=uuid4(), auth_user_id=OWNER_AUTH, first_name="Owner", last_name="Test",
            email="owner@example.test", role_id=owner_role.id,
        )
        session.add_all([customer, owner])
        session.flush()
        profile = Perfil(
            id=uuid4(), owner_user_id=owner.id, role_id=profile_role.id,
            kind="company", name="Transportes Test",
        )
        session.add(profile)
        session.flush()
        ids = []
        for _ in range(2):
            form = FormularioServicio(
                id=uuid4(), customer_id=customer.id, profile_id=profile.id,
                service_type_id=service_type.id, status="accepted",
            )
            session.add(form)
            session.flush()
            chat = Chat(id=uuid4(), form_id=form.id)
            session.add(chat)
            session.flush()
            quote = Cotizacion(
                id=uuid4(), chat_id=chat.id, status="paid", amount=Decimal("150000"),
                origin="A", destination="B", currency="CLP", service_type_id=service_type.id,
            )
            session.add(quote)
            session.flush()
            service = Servicio(
                id=uuid4(), profile_id=profile.id, customer_id=customer.id,
                form_id=form.id, accepted_quotation_id=quote.id, status="confirmed",
                amount=Decimal("150000"),
            )
            payment = Pago(
                id=uuid4(), quotation_id=quote.id, provider="simulated",
                provider_payment_id=f"sim_{uuid4().hex}", idempotency_key=f"test:{quote.id}",
                amount=Decimal("150000"), currency="CLP", status="approved",
            )
            session.add_all([service, payment])
            ids.append(service.id)
        session.commit()
    return ids


def test_postgres_concurrent_cancellation_and_start_row_lock(isolated_postgres):
    engine, schema = isolated_postgres
    first_id, second_id = seed_services(engine)

    def database():
        with Session(engine) as session:
            yield session

    def identity(x_actor: str = Header(default="customer")):
        return AuthenticatedUser(
            id=OWNER_AUTH if x_actor == "provider" else CUSTOMER_AUTH,
            email="test@example.test", session_id=uuid4(), assurance="aal2",
            authentication_methods=frozenset({"password", "phone"}),
        )

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_db_session] = database
    app.dependency_overrides[get_current_user] = identity
    try:
        with closing(TestClient(app)) as client:
            def cancel(role, service_id):
                return client.post(
                    f"/api/{role}/services/{service_id}/cancel", headers={"x-actor": role},
                )

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(cancel, role, first_id) for role in ("customer", "provider")]
                responses = [future.result(timeout=15) for future in futures]
            assert [response.status_code for response in responses] == [200, 200]
            assert responses[0].json()["cancellation"] == responses[1].json()["cancellation"]
            with Session(engine) as session:
                refunds = session.scalars(select(Reembolso)).all()
                assert len(refunds) == 1
                assert refunds[0].amount in (Decimal("135000"), Decimal("150000"))

            with Session(engine) as start_transaction, ThreadPoolExecutor(max_workers=1) as executor:
                row = start_transaction.execute(
                    select(Servicio).where(Servicio.id == second_id).with_for_update()
                ).scalar_one()
                pending = executor.submit(cancel, "customer", second_id)
                try:
                    deadline = time.monotonic() + 5
                    blocked = False
                    while time.monotonic() < deadline and not pending.done():
                        with engine.connect() as observer:
                            blocked = observer.scalar(text(
                                "SELECT EXISTS (SELECT 1 FROM pg_stat_activity "
                                "WHERE application_name = :name AND wait_event_type = 'Lock')"
                            ), {"name": schema})
                        if blocked:
                            break
                        time.sleep(0.05)
                    assert blocked, "Cancellation must wait on the service-start transaction's row lock"
                    row.status = "in_progress"
                    row.starts_at = utc_now()
                finally:
                    start_transaction.commit()
                response = pending.result(timeout=15)
            assert response.status_code == 409, response.text
            with Session(engine) as session:
                assert session.get(Servicio, second_id).status == "in_progress"
                assert len(session.scalars(select(Reembolso)).all()) == 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
