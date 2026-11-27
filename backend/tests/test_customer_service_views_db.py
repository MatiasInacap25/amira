"""Customer and provider service views over a real (SQLite) database.

The customer rating comes from a LEFT OUTER JOIN on Valoracion, and the list route takes origin and destination with
coalesce(form, quotation). These tests seed real rows so the SQL itself decides the result, not a fake row.
"""

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from amira_api.models import Chat, Cotizacion, FormularioServicio, Perfil, RolUsuario, Servicio, TipoServicio, Usuario, Valoracion
from chat_support import CUSTOMER_AUTH, PROVIDER_AUTH, api, db  # noqa: F401  (fixture re-export)

CREATED_AT = datetime(2026, 10, 1, 10, tzinfo=timezone.utc)
COMPLETED_AT = datetime(2026, 10, 5, 12, tzinfo=timezone.utc)
RATED_AT = datetime(2026, 10, 6, 9, 30, tzinfo=timezone.utc)


class World:
    def __init__(self, customer: Usuario, owner: Usuario, profile: Perfil, service_type: TipoServicio) -> None:
        self.customer = customer
        self.owner = owner
        self.profile = profile
        self.service_type = service_type


@pytest.fixture
def world(db: Session) -> World:
    roles = {code: RolUsuario(id=uuid4(), name=code, code=code) for code in ("client", "company_owner")}
    db.add_all(roles.values())
    customer = Usuario(id=uuid4(), auth_user_id=CUSTOMER_AUTH, first_name="Casey", last_name="Customer",
                       email="casey@example.test", role_id=roles["client"].id)
    owner = Usuario(id=uuid4(), auth_user_id=PROVIDER_AUTH, first_name="Pat", last_name="Owner",
                    email="pat@example.test", role_id=roles["company_owner"].id)
    db.add_all([customer, owner])
    db.flush()
    profile = Perfil(id=uuid4(), owner_user_id=owner.id, name="Transportes Norte", kind="company", role_id=uuid4())
    service_type = TipoServicio(id=uuid4(), name="Mudanzas", slug="mudanzas")
    db.add_all([profile, service_type])
    db.commit()
    return World(customer, owner, profile, service_type)


def add_service(
    db: Session,
    world: World,
    *,
    form_origin: str | None = None,
    form_destination: str | None = None,
    quote_origin: str = "Cotización Origen",
    quote_destination: str = "Cotización Destino",
) -> Servicio:
    """A completed service with an accepted quotation, built the way the quotation flow stores it."""
    form = FormularioServicio(
        id=uuid4(),
        profile_id=world.profile.id,
        service_type_id=world.service_type.id,
        origin=form_origin,
        destination=form_destination,
        status="accepted",
        customer_id=world.customer.id,
        is_exclusive=False,
        created_at=CREATED_AT,
    )
    chat = Chat(id=uuid4(), form_id=form.id, created_at=CREATED_AT)
    quote = Cotizacion(
        id=uuid4(),
        chat_id=chat.id,
        status="paid",
        amount=Decimal("150000"),
        origin=quote_origin,
        destination=quote_destination,
        service_type_id=world.service_type.id,
        currency="CLP",
        created_at=CREATED_AT,
    )
    service = Servicio(
        id=uuid4(),
        profile_id=world.profile.id,
        customer_id=world.customer.id,
        status="completed",
        description="Mover un sofá",
        created_at=CREATED_AT,
        completed_at=COMPLETED_AT,
        amount=Decimal("150000"),
        form_id=form.id,
        accepted_quotation_id=quote.id,
    )
    db.add_all([form, chat, quote, service])
    db.commit()
    return service


def rate(db: Session, world: World, service: Servicio) -> None:
    db.add(Valoracion(id=uuid4(), service_id=service.id, user_id=world.customer.id, rating=5,
                      comment="Buen servicio", created_at=RATED_AT))
    db.commit()


def as_rating_payload(rating: dict | None) -> dict | None:
    """SQLite returns naive datetimes (Postgres adds the UTC 'Z'), so compare the instant without the suffix."""
    if rating is None:
        return None
    return {**rating, "createdAt": rating["createdAt"].removesuffix("Z")}


RATING_PAYLOAD = {"rating": 5, "comment": "Buen servicio", "createdAt": "2026-10-06T09:30:00"}


# --- R3-001: the Valoracion join feeds the customer detail and list, never the provider detail -----------------------


def test_customer_detail_returns_the_rating_of_the_rated_service_and_null_for_the_other(api, db, world):
    rated = add_service(db, world)
    other = add_service(db, world)
    rate(db, world, rated)

    rated_detail = api(f"/api/customer/services/{rated.id}", as_auth_id=CUSTOMER_AUTH)
    other_detail = api(f"/api/customer/services/{other.id}", as_auth_id=CUSTOMER_AUTH)

    assert rated_detail.status_code == 200
    assert as_rating_payload(rated_detail.json()["rating"]) == RATING_PAYLOAD
    assert other_detail.status_code == 200
    assert other_detail.json()["rating"] is None


def test_customer_list_joins_the_rating_once_per_service_without_duplicating_rows(api, db, world):
    rated = add_service(db, world)
    other = add_service(db, world)
    rate(db, world, rated)

    response = api("/api/customer/services", as_auth_id=CUSTOMER_AUTH)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    ratings = {item["serviceId"]: as_rating_payload(item["rating"]) for item in body["items"]}
    assert ratings == {str(rated.id): RATING_PAYLOAD, str(other.id): None}


def test_provider_detail_of_the_rated_service_never_carries_the_rating(api, db, world):
    rated = add_service(db, world)
    rate(db, world, rated)

    response = api(f"/api/provider/services/{rated.id}", as_auth_id=PROVIDER_AUTH)

    assert response.status_code == 200
    assert response.json()["rating"] is None


# --- R3-003: list origin/destination are coalesce(form, quotation), the same rule as the detail ---------------------


@pytest.mark.parametrize("empty_form_value", [None, ""])
def test_list_falls_back_to_the_quotation_addresses_when_the_form_has_none(api, db, world, empty_form_value):
    service = add_service(
        db,
        world,
        form_origin=empty_form_value,
        form_destination=empty_form_value,
        quote_origin="Av. Cotización 1",
        quote_destination="Calle Cotización 2",
    )

    listing = api("/api/customer/services", as_auth_id=CUSTOMER_AUTH)
    detail = api(f"/api/customer/services/{service.id}", as_auth_id=CUSTOMER_AUTH)

    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert item["origin"] == "Av. Cotización 1"
    assert item["destination"] == "Calle Cotización 2"
    assert detail.json()["originAddress"] == item["origin"]
    assert detail.json()["destinationAddress"] == item["destination"]


def test_list_prefers_the_form_addresses_over_the_quotation_addresses(api, db, world):
    service = add_service(
        db,
        world,
        form_origin="Av. Providencia 1000",
        form_destination="Calle Los Aromos 45",
        quote_origin="Av. Cotización 1",
        quote_destination="Calle Cotización 2",
    )

    listing = api("/api/customer/services", as_auth_id=CUSTOMER_AUTH)
    detail = api(f"/api/customer/services/{service.id}", as_auth_id=CUSTOMER_AUTH)

    item = listing.json()["items"][0]
    assert item["origin"] == "Av. Providencia 1000"
    assert item["destination"] == "Calle Los Aromos 45"
    assert detail.json()["originAddress"] == item["origin"]
    assert detail.json()["destinationAddress"] == item["destination"]
