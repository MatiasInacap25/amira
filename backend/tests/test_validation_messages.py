import asyncio
from datetime import date, datetime, timedelta, timezone

import httpx
import pytest
from pydantic import ValidationError

from amira_api.account_schemas import AccountProvisionRequest
from amira_api.db import get_db_session
from amira_api.invitation_routes import InvitationCreate
from amira_api.main import app
from amira_api.public_schemas import ServiceRequestCreate


PERSONAL_RUT = "12345678-5"
COMPANY_RUT = "76123456-0"
PHONE = "+56912345678"
PROFILE_ID = "04db2a78-34fb-429e-ae9c-9fc5a9d10e32"
SERVICE_TYPE_ID = "6f6d0ae4-98ac-4a74-9a79-aac79443ed91"


def provider_values(**overrides):
    values = {
        "role": "company_owner",
        "first_name": "Casey",
        "last_name": "Owner",
        "national_id": PERSONAL_RUT,
        "birth_date": date(1990, 1, 1),
        "phone": PHONE,
        "display_name": "Casey Logistics",
        "company_tax_id": COMPANY_RUT,
        "commune_code": "13101",
    }
    values.update(overrides)
    return values


def single_error(model, values) -> dict:
    with pytest.raises(ValidationError) as error:
        model(**values)
    errors = error.value.errors()
    assert len(errors) == 1, errors
    return errors[0]


@pytest.mark.parametrize(
    ("overrides", "field", "message", "error_type"),
    [
        ({"national_id": "12345678-0"}, "national_id", "Ingresa un RUT chileno válido.", "rut_invalid"),
        ({"company_tax_id": "76123456-1"}, "company_tax_id", "Ingresa un RUT chileno válido.", "rut_invalid"),
        ({"phone": "+0912345678"}, "phone", "Ingresa un teléfono en formato internacional, por ejemplo +56912345678.", "phone_invalid"),
        ({"birth_date": date(2099, 1, 1)}, "birth_date", "Ingresa una fecha de nacimiento válida.", "birth_date_invalid"),
    ],
)
def test_field_validator_messages_are_spanish_and_keep_the_field_location(overrides, field, message, error_type):
    error = single_error(AccountProvisionRequest, provider_values(**overrides))

    assert error["loc"] == (field,)
    assert error["msg"] == message
    assert error["type"] == error_type


def test_cross_field_provider_messages_are_spanish():
    error = single_error(AccountProvisionRequest, provider_values(commune_code=None))
    assert error["msg"] == "Selecciona una comuna del catálogo para tu cuenta de proveedor."
    assert error["type"] == "commune_required"

    error = single_error(AccountProvisionRequest, provider_values(company_tax_id=None))
    assert error["msg"] == "Las cuentas de empresa requieren un RUT de empresa."
    assert error["type"] == "company_tax_id_required"

    client_error = single_error(
        AccountProvisionRequest,
        {"role": "client", "first_name": "Casey", "last_name": "Client", "national_id": PERSONAL_RUT, "birth_date": date(1990, 1, 1), "phone": PHONE, "commune_code": "13101"},
    )
    assert client_error["msg"] == "Las cuentas de cliente no pueden incluir datos de perfil de proveedor."
    assert client_error["type"] == "client_provider_fields"


def test_quote_request_messages_are_spanish_for_timezone_and_past_dates():
    base = {"profileId": PROFILE_ID, "serviceTypeId": SERVICE_TYPE_ID, "originCommuneCode": "13101", "destinationCommuneCode": "05101"}

    naive = single_error(ServiceRequestCreate, {**base, "requestedAt": "2026-11-08T10:00:00"})
    assert naive["msg"] == "La fecha solicitada debe incluir zona horaria."
    assert naive["type"] == "requested_at_timezone"

    past = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    past_error = single_error(ServiceRequestCreate, {**base, "requestedAt": past})
    assert past_error["loc"] == ("requestedAt",)
    assert past_error["msg"] == "La fecha solicitada no puede estar en el pasado."
    assert past_error["type"] == "requested_at_past"


def test_invitation_email_message_is_spanish():
    error = single_error(InvitationCreate, {"email": "not-an-email"})

    assert error["loc"] == ("email",)
    assert error["msg"] == "Ingresa un correo electrónico válido."
    assert error["type"] == "email_invalid"


def test_departure_window_errors_keep_the_422_list_shape_with_spanish_messages():
    response = asyncio.run(_get_shared_routes({"departureFrom": "2026-10-31T00:00:00Z", "departureTo": "2026-10-01T00:00:00Z"}))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"] == ["query", "departureFrom"]
    assert detail[0]["msg"] == "La salida inicial no puede ser posterior a la salida final."
    assert detail[0]["type"] == "departure_window_inverted"


def test_departure_timezone_errors_keep_the_422_list_shape_with_spanish_messages():
    response = asyncio.run(_get_shared_routes({"departureFrom": "2026-10-01T00:00:00"}))

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["query", "departureFrom"]
    assert detail[0]["msg"] == "Las fechas de salida deben incluir zona horaria."
    assert detail[0]["type"] == "departure_timezone"


async def _get_shared_routes(params: dict) -> httpx.Response:
    class _EmptySession:
        def execute(self, statement):  # pragma: no cover - validation fails before any query
            raise AssertionError("validation must fail before the database is queried")

    app.dependency_overrides[get_db_session] = lambda: _EmptySession()
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.get("/api/shared-routes", params=params)
    finally:
        app.dependency_overrides.pop(get_db_session, None)
