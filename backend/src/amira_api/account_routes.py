"""Server-owned account provisioning; roles come only from validated input."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from amira_api.account_schemas import AccountProvisionRequest, AccountResponse, AccountRole, AccountRoleCode, CompanyTransitionRequest
from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.models import Conductor, Perfil, RolPerfil, RolUsuario, TipoConductor, Usuario
from amira_api.settings import Settings, get_settings

router = APIRouter(prefix="/api/account", tags=["account"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]


@router.get("/me", response_model=AccountResponse)
def get_account(current_user: CurrentUser, session: Database) -> AccountResponse:
    result = session.execute(
        select(Usuario, RolUsuario.code)
        .join(RolUsuario, Usuario.role_id == RolUsuario.id)
        .where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Account is not provisioned.")
    user, role_code = result
    profile = session.execute(select(Perfil.id).where(Perfil.owner_user_id == user.id)).scalar_one_or_none()
    return AccountResponse(user_id=user.id, role=AccountRoleCode(role_code), profile_id=profile)


@router.post("/company/transition", response_model=AccountResponse)
def transition_to_company(
    payload: CompanyTransitionRequest,
    current_user: CurrentUser,
    session: Database,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AccountResponse:
    if settings.company_driver_type_id is None:
        raise HTTPException(status_code=503, detail="Company-linked driver provisioning is not configured.")

    owner_result = session.execute(
        select(Usuario, RolUsuario.code)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Usuario.auth_user_id == current_user.id)
        .with_for_update()
    ).one_or_none()
    if owner_result is None:
        raise HTTPException(status_code=403, detail="A provisioned provider owner account is required.")
    owner, owner_role_code = owner_result
    if owner_role_code not in {"independent_driver", "company_owner"}:
        raise HTTPException(status_code=403, detail="Only a provider profile owner can add a company driver.")
    if payload.driver_user_id == owner.id:
        raise HTTPException(status_code=409, detail="The profile owner cannot be added as a second driver.")

    profile_result = session.execute(
        select(Perfil, RolPerfil.code)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .where(Perfil.owner_user_id == owner.id)
        .with_for_update()
    ).one_or_none()
    if profile_result is None:
        raise HTTPException(status_code=403, detail="An owned provider profile is required.")
    profile, profile_role_code = profile_result
    if profile_role_code != profile.kind or profile.kind not in {"company", "independent_driver"}:
        raise HTTPException(status_code=409, detail="Provider profile role is inconsistent.")
    if (owner_role_code, profile.kind) not in {
        ("independent_driver", "independent_driver"),
        ("company_owner", "company"),
    }:
        raise HTTPException(status_code=409, detail="Provider account and profile roles are inconsistent.")
    if owner_role_code == "independent_driver" and profile.company_tax_id not in {None, payload.company_tax_id}:
        raise HTTPException(status_code=409, detail="Company tax ID conflicts with existing profile data.")
    if owner_role_code == "company_owner" and profile.company_tax_id != payload.company_tax_id:
        raise HTTPException(status_code=409, detail="Company tax ID does not match the existing profile.")

    owner_driver = session.execute(
        select(Conductor).where(Conductor.user_id == owner.id).with_for_update()
    ).scalar_one_or_none()
    if owner_driver is None or owner_driver.employer_profile_id not in {None, profile.id}:
        raise HTTPException(status_code=409, detail="The profile owner's existing driver record cannot be linked safely.")

    company_profile_role = session.execute(
        select(RolPerfil).where(RolPerfil.code == "company")
    ).scalar_one_or_none()
    company_owner_role = session.execute(
        select(RolUsuario).where(RolUsuario.code == "company_owner")
    ).scalar_one_or_none()
    company_driver_role = session.execute(
        select(RolUsuario).where(RolUsuario.code == "company_driver")
    ).scalar_one_or_none()
    driver_type = session.execute(
        select(TipoConductor).where(TipoConductor.id == settings.company_driver_type_id)
    ).scalar_one_or_none()
    if None in (company_profile_role, company_owner_role, company_driver_role, driver_type):
        raise HTTPException(status_code=503, detail="Company profile, account role, or driver type mapping is invalid.")

    driver_result = session.execute(
        select(Usuario, RolUsuario.code)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Usuario.id == payload.driver_user_id)
        .with_for_update()
    ).one_or_none()
    if driver_result is None:
        raise HTTPException(status_code=404, detail="The invited driver account was not found.")
    driver_user, driver_role_code = driver_result
    driver_profile = session.execute(
        select(Perfil.id).where(Perfil.owner_user_id == driver_user.id)
    ).scalar_one_or_none()
    linked_driver = session.execute(
        select(Conductor).where(Conductor.user_id == driver_user.id).with_for_update()
    ).scalar_one_or_none()

    if driver_role_code == "company_driver":
        if driver_profile is not None or linked_driver is None or linked_driver.employer_profile_id != profile.id:
            raise HTTPException(status_code=409, detail="Driver account is already linked elsewhere.")
        if linked_driver.driver_type_id != driver_type.id:
            raise HTTPException(status_code=409, detail="Existing linked driver type does not match configuration.")
    elif driver_role_code == "client":
        if driver_profile is not None or linked_driver is not None:
            raise HTTPException(status_code=409, detail="Only an unlinked client account can become a company driver.")
    else:
        raise HTTPException(status_code=409, detail="Only an unlinked client account can become a company driver.")

    try:
        if owner_role_code == "independent_driver":
            owner.role_id = company_owner_role.id
            profile.kind = "company"
            profile.role_id = company_profile_role.id
            profile.company_tax_id = payload.company_tax_id
        owner_driver.employer_profile_id = profile.id
        if driver_role_code == "client":
            driver_user.role_id = company_driver_role.id
            session.add(Conductor(
                user_id=driver_user.id,
                employer_profile_id=profile.id,
                driver_type_id=driver_type.id,
            ))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return AccountResponse(user_id=owner.id, role=AccountRoleCode.COMPANY_OWNER, profile_id=profile.id)


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
        ):
            raise HTTPException(status_code=409, detail="Profile details do not match the existing account.")
        profile_id = profile.id

        if payload.role == AccountRole.INDEPENDENT_DRIVER:
            if settings.independent_driver_type_id is None:
                raise HTTPException(status_code=503, detail="Independent driver provisioning is not configured.")
            driver = session.execute(select(Conductor).where(Conductor.user_id == user.id)).scalar_one_or_none()
            if driver is None:
                driver = Conductor(user_id=user.id, employer_profile_id=None, driver_type_id=settings.independent_driver_type_id)
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
