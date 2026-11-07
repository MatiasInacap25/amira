from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from amira_api.db import get_db_session
from amira_api.main import app
from amira_api.models import TipoServicio

SERVICE_MOVING = UUID("a1000000-0000-4000-8000-000000000001")
SERVICE_SHARED = UUID("a1000000-0000-4000-8000-000000000006")


@pytest.fixture
def client():
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE TABLE "Tipos_Servicio" ("ID" CHAR(32) PRIMARY KEY, "Nombre_servicio" VARCHAR(120) NOT NULL, "Slug" VARCHAR(120) NOT NULL)'
        ))
    with Session(engine) as session:
        session.add_all([
            TipoServicio(id=SERVICE_MOVING, name="Mudanza", slug="mudanza"),
            TipoServicio(id=SERVICE_SHARED, name="Carga compartida", slug="carga-compartida"),
        ])
        session.commit()
        app.dependency_overrides[get_db_session] = lambda: session
        yield TestClient(app)
        app.dependency_overrides.pop(get_db_session, None)
    engine.dispose()


def test_service_types_endpoint_omits_hidden_carga_compartida(client) -> None:
    response = client.get("/api/service-types")

    assert response.status_code == 200
    assert response.json() == {"items": [{"id": str(SERVICE_MOVING), "slug": "mudanza", "name": "Mudanza"}]}


def test_service_types_endpoint_still_lists_other_types_as_before(client) -> None:
    response = client.get("/api/service-types")

    assert response.status_code == 200
    assert "mudanza" in [item["slug"] for item in response.json()["items"]]
