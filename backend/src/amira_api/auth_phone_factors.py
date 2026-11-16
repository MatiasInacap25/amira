"""Reads a user's SMS-verified phone factors from Supabase Auth, to trust a phone change only after its SMS code.

GET {SUPABASE_URL}/auth/v1/admin/users/{id} with the service-role key. The key is server-side only and never reaches a
log line or an exception message. Any answer this adapter does not understand is AuthAdminUnavailable, so an unexpected
shape can never be read as a verified number.
"""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

import httpx

REQUEST_TIMEOUT_SECONDS = 10.0


@dataclass(frozen=True)
class PhoneFactor:
    id: UUID
    # Supabase stores the number as digits only, without the leading +.
    phone: str


class AuthAdminUnavailable(Exception):
    """Supabase Auth could not be reached or answered something unexpected."""


class PhoneFactorReader(Protocol):
    def verified_phone_factors(self, auth_user_id: UUID) -> list[PhoneFactor]: ...


class SupabasePhoneFactorReader:
    def __init__(self, *, url: str, service_role_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._base_url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key}
        self._transport = transport

    def verified_phone_factors(self, auth_user_id: UUID) -> list[PhoneFactor]:
        try:
            with httpx.Client(base_url=self._base_url, headers=self._headers, timeout=REQUEST_TIMEOUT_SECONDS,
                              transport=self._transport) as client:
                response = client.get(f"/auth/v1/admin/users/{auth_user_id}")
        except httpx.HTTPError as error:
            raise AuthAdminUnavailable("Supabase Auth could not be reached.") from error
        if response.status_code != 200:
            raise AuthAdminUnavailable(f"Supabase Auth answered HTTP {response.status_code}.")
        try:
            return _verified_phones(response.json())
        except (ValueError, KeyError, TypeError, AttributeError) as error:
            raise AuthAdminUnavailable("Supabase Auth answered an unexpected user shape.") from error


def _verified_phones(body: Any) -> list[PhoneFactor]:
    factors = body.get("factors") or []
    if not isinstance(factors, list):
        raise TypeError("factors is not a list")
    return [
        PhoneFactor(id=UUID(item["id"]), phone=str(item["phone"]))
        for item in factors
        if item.get("factor_type") == "phone" and item.get("status") == "verified"
    ]
