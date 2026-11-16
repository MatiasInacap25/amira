"""Server-owned account provisioning; roles come only from validated input."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.account_schemas import (
    AccountDetailsResponse,
    AccountProvisionRequest,
    AccountResponse,
    AccountRole,
    AccountRoleCode,
    PhoneChangeRequest,
)
from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.auth_phone_factors import AuthAdminUnavailable, PhoneFactorReader, SupabasePhoneFactorReader
from amira_api.db import get_db_session
from amira_api.models import Commune, Conductor, Perfil, RolPerfil, RolUsuario, TipoConductor, Usuario
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/api/account", tags=["account"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
PHONE_NOT_VERIFIED = "Verifica el número nuevo con el código SMS antes de guardarlo."


def get_phone_factor_reader(settings: Annotated[Settings, Depends(get_settings)]) -> PhoneFactorReader:
    if not settings.supabase_url or settings.supabase_service_role_key is None:
        raise HTTPException(status_code=503, detail="Phone changes are not configured.")
    return SupabasePhoneFactorReader(
        url=settings.supabase_url, service_role_key=settings.supabase_service_role_key.get_secret_value(),
    )


def _account_details(session: Session, user: Usuario, role_code: str) -> AccountDetailsResponse:
    profile = session.execute(select(Perfil.id).where(Perfil.owner_user_id == user.id)).scalar_one_or_none()
    return AccountDetailsResponse(
        user_id=user.id, role=AccountRoleCode(role_code), profile_id=profile, first_name=user.first_name,
        last_name=user.last_name, national_id=user.national_id, phone=user.phone,
    )


@router.get("/me", response_model=AccountDetailsResponse)
def get_account(current_user: CurrentUser, session: Database) -> AccountDetailsResponse:
    result = session.execute(
        select(Usuario, RolUsuario.code)
        .join(RolUsuario, Usuario.role_id == RolUsuario.id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Account is not provisioned.")
    user, role_code = result
    return _account_details(session, user, role_code)


@router.put("/phone", response_model=AccountDetailsResponse)
def change_phone(
    payload: PhoneChangeRequest,
    current_user: CurrentUser,
    session: Database,
    factors: Annotated[PhoneFactorReader, Depends(get_phone_factor_reader)],
) -> AccountDetailsResponse:
    """Saves a new phone only when this session passed SMS and Supabase holds that number as the given verified factor."""
    if current_user.assurance != "aal2":
        raise HTTPException(status_code=403, detail=PHONE_NOT_VERIFIED)
    result = session.execute(
        select(Usuario, RolUsuario.code)
        .join(RolUsuario, Usuario.role_id == RolUsuario.id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Account is not provisioned.")
    user, role_code = result
    try:
        verified = factors.verified_phone_factors(current_user.id)
    except AuthAdminUnavailable:
        raise HTTPException(status_code=503, detail="No pudimos comprobar el número. Inténtalo más tarde.") from None
    digits = payload.phone.removeprefix("+")
    if not any(factor.id == payload.factor_id and factor.phone.removeprefix("+") == digits for factor in verified):
        raise HTTPException(status_code=422, detail=PHONE_NOT_VERIFIED)
    user.phone = payload.phone
    session.commit()
    return _account_details(session, user, role_code)


@router.post("/provision", response_model=AccountResponse, status_code=201)
def provision_account(
    payload: AccountProvisionRequest,
    current_user: CurrentUser,
    session: Database,
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
) -> AccountResponse:
    company_driver_type: TipoConductor | None = None
    if payload.also_driver:
        if settings.company_driver_type_id is None:
            raise HTTPException(status_code=503, detail="Company-linked driver provisioning is not configured.")
        company_driver_type = session.execute(
            select(TipoConductor).where(TipoConductor.id == settings.company_driver_type_id)
        ).scalar_one_or_none()
        if company_driver_type is None:
            raise HTTPException(status_code=503, detail="Company-linked driver type mapping is invalid.")

    if payload.commune_code is not None:
        commune_exists = session.execute(select(Commune.code).where(Commune.code == payload.commune_code)).scalar_one_or_none()
        if commune_exists is None:
            raise HTTPException(
                status_code=422,
                detail=[
                    {
                        "loc": ["body", "commune_code"],
                        "msg": "Selecciona una comuna válida del catálogo.",
                        "type": "value_error",
                    }
                ],
            )

    role_code = payload.role.value
    account_role = session.execute(select(RolUsuario).where(RolUsuario.code == role_code)).scalar_one_or_none()
    if account_role is None:
        raise HTTPException(status_code=503, detail="Account roles are not configured.")

    user = session.execute(select(Usuario).where(Usuario.auth_user_id == current_user.id)).scalar_one_or_none()
    created = user is None
    if created:
        user = Usuario(
            auth_user_id=current_user.id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=current_user.email,
            national_id=payload.national_id,
            birth_date=payload.birth_date,
            phone=payload.phone,
            role_id=account_role.id,
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            user = session.execute(select(Usuario).where(Usuario.auth_user_id == current_user.id)).scalar_one_or_none()
            if (
                user is None
                or user.role_id != account_role.id
                or user.first_name != payload.first_name
                or user.last_name != payload.last_name
                or user.email != current_user.email
                or user.national_id != payload.national_id
                or user.birth_date != payload.birth_date
                or user.phone != payload.phone
            ):
                raise HTTPException(status_code=409, detail="Account provisioning conflicted; retry safely.") from None
            created = False
    elif user.role_id != account_role.id:
        raise HTTPException(status_code=409, detail="An account already exists with a different role.")
    elif (
        user.first_name != payload.first_name
        or user.last_name != payload.last_name
        or user.email != current_user.email
        or (user.national_id is not None and user.national_id != payload.national_id)
        or (user.birth_date is not None and user.birth_date != payload.birth_date)
        or (user.phone is not None and user.phone != payload.phone)
    ):
        raise HTTPException(status_code=409, detail="Account details do not match the existing account.")
    else:
        # Older auth-only accounts can complete these private fields exactly once.
        if user.national_id is None:
            user.national_id = payload.national_id
        if user.birth_date is None:
            user.birth_date = payload.birth_date
        if user.phone is None:
            user.phone = payload.phone

    profile_id: UUID | None = None
    if payload.role in (AccountRole.COMPANY_OWNER, AccountRole.INDEPENDENT_DRIVER):
        kind = "company" if payload.role == AccountRole.COMPANY_OWNER else "independent_driver"
        profile_role = session.execute(select(RolPerfil).where(RolPerfil.code == kind)).scalar_one_or_none()
        if profile_role is None:
            raise HTTPException(status_code=503, detail="Provider profile roles are not configured.")
        profile = session.execute(select(Perfil).where(Perfil.owner_user_id == user.id)).scalar_one_or_none()
        if profile is None:
            profile = Perfil(
                owner_user_id=user.id,
                name=payload.display_name,
                role_id=profile_role.id,
                kind=kind,
                company_tax_id=payload.company_tax_id,
                commune_code=payload.commune_code,
            )
            session.add(profile)
            try:
                session.flush()
            except IntegrityError:
                session.rollback()
                profile = session.execute(select(Perfil).where(Perfil.owner_user_id == user.id)).scalar_one_or_none()
                if (
                    profile is None
                    or profile.kind != kind
                    or profile.name != payload.display_name
                    or profile.company_tax_id != payload.company_tax_id
                    or profile.role_id != profile_role.id
                ):
                    raise HTTPException(status_code=409, detail="Profile provisioning conflicted; retry safely.") from None
        elif (
            profile.kind != kind
            or profile.name != payload.display_name
            or profile.company_tax_id != payload.company_tax_id
            or profile.role_id != profile_role.id
            or (profile.commune_code is not None and profile.commune_code != payload.commune_code)
        ):
            raise HTTPException(status_code=409, detail="Profile details do not match the existing account.")
        if profile.commune_code is None:
            # Profiles created before the commune catalog can complete their location exactly once.
            profile.commune_code = payload.commune_code
        profile_id = profile.id

        if payload.role == AccountRole.INDEPENDENT_DRIVER:
            if settings.independent_driver_type_id is None:
                raise HTTPException(status_code=503, detail="Independent driver provisioning is not configured.")
            driver = session.execute(select(Conductor).where(Conductor.user_id == user.id)).scalar_one_or_none()
            if driver is None:
                driver = Conductor(
                    user_id=user.id,
                    employer_profile_id=None,
                    driver_type_id=settings.independent_driver_type_id,
                    commune_code=payload.commune_code,
                )
                session.add(driver)
                try:
                    session.flush()
                except IntegrityError:
                    session.rollback()
                    driver = session.execute(select(Conductor).where(Conductor.user_id == user.id)).scalar_one_or_none()
                    if driver is None or driver.employer_profile_id is not None or driver.driver_type_id != settings.independent_driver_type_id:
                        raise HTTPException(status_code=409, detail="Driver provisioning conflicted; retry safely.") from None
            elif driver.employer_profile_id is not None or driver.driver_type_id != settings.independent_driver_type_id:
                raise HTTPException(status_code=409, detail="Existing driver record does not match independent-driver role.")
            elif driver.commune_code is None:
                driver.commune_code = payload.commune_code
        elif payload.role == AccountRole.COMPANY_OWNER:
            driver = session.execute(select(Conductor).where(Conductor.user_id == user.id)).scalar_one_or_none()
            if payload.also_driver:
                if company_driver_type is None:
                    raise HTTPException(status_code=503, detail="Company-linked driver type mapping is unavailable.")
                if driver is None:
                    driver = Conductor(
                        user_id=user.id,
                        employer_profile_id=profile.id,
                        driver_type_id=company_driver_type.id,
                        commune_code=payload.commune_code,
                    )
                    session.add(driver)
                    try:
                        session.flush()
                    except IntegrityError:
                        session.rollback()
                        driver = session.execute(select(Conductor).where(Conductor.user_id == user.id)).scalar_one_or_none()
                        if (
                            driver is None
                            or driver.employer_profile_id != profile.id
                            or driver.driver_type_id != company_driver_type.id
                        ):
                            raise HTTPException(status_code=409, detail="Company-linked driver provisioning conflicted; retry safely.") from None
                elif driver.employer_profile_id != profile.id or driver.driver_type_id != company_driver_type.id:
                    raise HTTPException(status_code=409, detail="Existing driver record does not match company-linked role.")
            elif driver is not None:
                raise HTTPException(status_code=409, detail="Existing driver record does not match the selected account capabilities.")

    session.commit()
    response.status_code = 201 if created else 200
    return AccountResponse(user_id=user.id, role=AccountRoleCode(payload.role.value), profile_id=profile_id)
