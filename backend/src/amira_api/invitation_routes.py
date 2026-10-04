"""Owner-managed, one-use invitations for company-linked drivers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from typing import Annotated, Protocol
from urllib.parse import urlencode, urlsplit, urlunsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.db import get_db_session
from amira_api.models import Conductor, DriverInvitation, Perfil, RolPerfil, RolUsuario, TipoConductor, Usuario
from amira_api.settings import Settings, get_settings

router = APIRouter(tags=["company invitations"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
INVITATION_TTL = timedelta(days=7)
ISSUE_WINDOW = timedelta(minutes=15)
MAX_ISSUES_PER_WINDOW = 5
INVALID_INVITATION = "Invitation is invalid or expired."


class InvitationSender(Protocol):
    def send_invitation(self, email: str, link: str) -> bool: ...


class EmailConfirmationVerifier(Protocol):
    def is_confirmed(self, access_token: str, user_id: UUID, email: str) -> bool: ...


def get_invitation_sender(settings: Annotated[Settings, Depends(get_settings)]) -> InvitationSender | None:
    if not settings.resend_api_key or not settings.invitation_sender_email or not settings.frontend_base_url:
        return None
    return ResendInvitationSender(settings.resend_api_key.get_secret_value(), settings.invitation_sender_email)


def get_email_confirmation_verifier(settings: Annotated[Settings, Depends(get_settings)]) -> EmailConfirmationVerifier | None:
    if not settings.supabase_jwt_issuer or not settings.supabase_publishable_key:
        return None
    return SupabaseEmailConfirmationVerifier(
        settings.supabase_jwt_issuer.rstrip("/"), settings.supabase_publishable_key.get_secret_value(),
    )


class SupabaseEmailConfirmationVerifier:
    """Confirms email from Supabase Auth's authenticated user endpoint, not JWT email alone."""

    def __init__(self, auth_url: str, publishable_key: str):
        self._user_endpoint = f"{auth_url}/user"
        self._publishable_key = publishable_key

    def is_confirmed(self, access_token: str, user_id: UUID, email: str) -> bool:
        try:
            response = httpx.get(
                self._user_endpoint,
                headers={"apikey": self._publishable_key, "Authorization": f"Bearer {access_token}"},
                timeout=3.0,
            )
            if not response.is_success:
                return False
            data = response.json()
            return (
                isinstance(data, dict)
                and data.get("id") == str(user_id)
                and isinstance(data.get("email"), str)
                and _normalize_email(data["email"]) == email
                and bool(data.get("email_confirmed_at"))
            )
        except Exception:
            return False


class ResendInvitationSender:
    """Configured Resend transport; never logs provider responses or invitation links."""

    def __init__(self, api_key: str, sender_email: str):
        self._api_key = api_key
        self._sender_email = sender_email

    def send_invitation(self, email: str, link: str) -> bool:
        try:
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "from": self._sender_email,
                    "to": [email],
                    "subject": "Invitación para unirte a una empresa en Amira",
                    "html": f'<p>Una empresa te invitó a unirte a Amira.</p><p><a href="{link}">Revisar invitación</a></p>',
                },
                timeout=5.0,
            )
            return response.is_success
        except Exception:
            return False


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized.count("@") != 1 or any(char.isspace() for char in normalized):
            raise ValueError("Enter a valid email address.")
        local, domain = normalized.split("@")
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("Enter a valid email address.")
        return normalized


class InvitationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class InvitationItem(BaseModel):
    id: UUID
    email: str
    created_at: datetime
    expires_at: datetime
    status: str


class InvitationList(BaseModel):
    invitations: list[InvitationItem]


class InvitationResult(BaseModel):
    id: UUID
    email: str
    expires_at: datetime


class InvitationAccepted(BaseModel):
    user_id: UUID
    role: str = "company_driver"
    profile_id: UUID


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _invitation_status(invitation: DriverInvitation, now: datetime) -> str:
    if invitation.accepted_at is not None:
        return "accepted"
    if invitation.revoked_at is not None:
        return "revoked"
    if invitation.expires_at <= now:
        return "expired"
    return "pending"


def _owned_company(session: Session, auth_user_id: UUID, *, lock: bool = False):
    statement = (
        select(Usuario, Perfil)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .join(Perfil, Perfil.owner_user_id == Usuario.id)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .where(Usuario.auth_user_id == auth_user_id, RolUsuario.code == "company_owner", Perfil.kind == "company", RolPerfil.code == "company")
    )
    if lock:
        statement = statement.with_for_update()
    result = session.execute(statement).one_or_none()
    if result is None:
        raise HTTPException(status_code=403, detail="A company owner profile is required.")
    return result


def _new_invitation(session: Session, owner: Usuario, profile: Perfil, email: str, settings: Settings, sender: InvitationSender) -> InvitationResult:
    configured_base = settings.frontend_base_url
    parsed_base = urlsplit(configured_base or "")
    if (
        parsed_base.scheme not in {"https", "http"}
        or not parsed_base.netloc
        or parsed_base.username is not None
        or parsed_base.password is not None
        or parsed_base.query
        or parsed_base.fragment
    ):
        raise HTTPException(status_code=503, detail="Invitation delivery is not configured.")
    now = datetime.now(timezone.utc)
    recent_count = session.execute(
        select(func.count()).select_from(DriverInvitation).where(
            DriverInvitation.company_profile_id == profile.id,
            DriverInvitation.created_by_user_id == owner.id,
            DriverInvitation.created_at >= now - ISSUE_WINDOW,
        )
    ).scalar_one()
    if recent_count >= MAX_ISSUES_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Invitation rate limit exceeded.")

    token = secrets.token_urlsafe(32)
    invitation = DriverInvitation(
        company_profile_id=profile.id,
        target_email=email,
        token_hash=hashlib.sha256(token.encode("ascii")).hexdigest(),
        created_by_user_id=owner.id,
        expires_at=now + INVITATION_TTL,
    )
    session.execute(
        update(DriverInvitation)
        .where(
            DriverInvitation.company_profile_id == profile.id,
            DriverInvitation.target_email == email,
            DriverInvitation.accepted_at.is_(None),
            DriverInvitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    session.add(invitation)
    session.flush()
    path = f"{parsed_base.path.rstrip('/')}/invitacion/conductor"
    # Keep the raw token in the fragment; browsers do not send it to the web server.
    link = urlunsplit((parsed_base.scheme, parsed_base.netloc, path, "", urlencode({"token": token})))
    try:
        delivered = sender.send_invitation(email, link)
    except Exception:
        session.rollback()
        raise HTTPException(status_code=503, detail="Invitation delivery is unavailable.") from None
    if delivered is not True:
        session.rollback()
        raise HTTPException(status_code=503, detail="Invitation delivery is unavailable.")
    session.commit()
    return InvitationResult(id=invitation.id, email=email, expires_at=invitation.expires_at)


@router.post("/api/company/profiles/me/driver-invitations", response_model=InvitationResult, status_code=201)
def create_invitation(
    payload: InvitationCreate,
    current_user: CurrentUser,
    session: Database,
    settings: Annotated[Settings, Depends(get_settings)],
    sender: Annotated[InvitationSender | None, Depends(get_invitation_sender)],
) -> InvitationResult:
    if sender is None:
        raise HTTPException(status_code=503, detail="Invitation delivery is not configured.")
    owner, profile = _owned_company(session, current_user.id, lock=True)
    return _new_invitation(session, owner, profile, _normalize_email(payload.email), settings, sender)


@router.get("/api/company/profiles/me/driver-invitations", response_model=InvitationList)
def list_invitations(current_user: CurrentUser, session: Database) -> InvitationList:
    _, profile = _owned_company(session, current_user.id)
    rows = session.execute(
        select(DriverInvitation).where(DriverInvitation.company_profile_id == profile.id)
        .order_by(DriverInvitation.created_at.desc(), DriverInvitation.id.desc())
    ).scalars().all()
    now = datetime.now(timezone.utc)
    return InvitationList(invitations=[
        InvitationItem(id=row.id, email=row.target_email, created_at=row.created_at,
                       expires_at=row.expires_at, status=_invitation_status(row, now))
        for row in rows
    ])


@router.delete("/api/company/profiles/me/driver-invitations/{invitation_id}", response_model=InvitationResult)
def revoke_invitation(invitation_id: UUID, current_user: CurrentUser, session: Database) -> InvitationResult:
    _, profile = _owned_company(session, current_user.id, lock=True)
    invitation = session.execute(
        select(DriverInvitation).where(
            DriverInvitation.id == invitation_id,
            DriverInvitation.company_profile_id == profile.id,
        ).with_for_update()
    ).scalar_one_or_none()
    if invitation is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if _invitation_status(invitation, datetime.now(timezone.utc)) != "pending":
        raise HTTPException(status_code=409, detail="Only a pending invitation can be revoked.")
    invitation.revoked_at = datetime.now(timezone.utc)
    session.commit()
    return InvitationResult(id=invitation.id, email=invitation.target_email, expires_at=invitation.expires_at)


@router.post("/api/company/profiles/me/driver-invitations/{invitation_id}/reissue", response_model=InvitationResult, status_code=201)
def reissue_invitation(
    invitation_id: UUID,
    current_user: CurrentUser,
    session: Database,
    settings: Annotated[Settings, Depends(get_settings)],
    sender: Annotated[InvitationSender | None, Depends(get_invitation_sender)],
) -> InvitationResult:
    if sender is None:
        raise HTTPException(status_code=503, detail="Invitation delivery is not configured.")
    owner, profile = _owned_company(session, current_user.id, lock=True)
    previous = session.execute(
        select(DriverInvitation).where(
            DriverInvitation.id == invitation_id,
            DriverInvitation.company_profile_id == profile.id,
        ).with_for_update()
    ).scalar_one_or_none()
    if previous is None:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    if previous.accepted_at is not None:
        raise HTTPException(status_code=409, detail="An accepted invitation cannot be reissued.")
    previous.revoked_at = datetime.now(timezone.utc)
    return _new_invitation(session, owner, profile, previous.target_email, settings, sender)


@router.post("/api/driver-invitations/accept", response_model=InvitationAccepted)
def accept_invitation(
    payload: InvitationAccept,
    current_user: CurrentUser,
    session: Database,
    settings: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
    email_verifier: Annotated[EmailConfirmationVerifier | None, Depends(get_email_confirmation_verifier)] = None,
) -> InvitationAccepted:
    if email_verifier is None:
        raise HTTPException(status_code=503, detail="Email confirmation verification is not configured.")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authentication credentials.")
    access_token = authorization.removeprefix("Bearer ").strip()
    if not access_token or not email_verifier.is_confirmed(access_token, current_user.id, _normalize_email(current_user.email)):
        raise HTTPException(status_code=403, detail="A confirmed email identity is required.")
    if settings.company_driver_type_id is None:
        raise HTTPException(status_code=503, detail="Company-linked driver provisioning is not configured.")
    token_hash = hashlib.sha256(payload.token.encode("ascii")).hexdigest()
    candidate_profile_id = session.execute(
        select(DriverInvitation.company_profile_id).where(DriverInvitation.token_hash == token_hash)
    ).scalar_one_or_none()
    if candidate_profile_id is None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    profile_result = session.execute(
        select(Perfil, RolPerfil.code, RolUsuario.code)
        .join(RolPerfil, RolPerfil.id == Perfil.role_id)
        .join(Usuario, Usuario.id == Perfil.owner_user_id)
        .join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Perfil.id == candidate_profile_id).with_for_update()
    ).one_or_none()
    if profile_result is None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    profile, profile_role, owner_role = profile_result
    if profile.kind != "company" or profile_role != "company" or owner_role != "company_owner":
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)

    # Keep the lock order profile -> invitation -> invitee, matching owner
    # reissue/revoke and preventing a profile/invitation deadlock.
    invitation = session.execute(
        select(DriverInvitation).where(
            DriverInvitation.token_hash == token_hash,
            DriverInvitation.company_profile_id == profile.id,
        ).with_for_update()
    ).scalar_one_or_none()
    if invitation is None or _invitation_status(invitation, datetime.now(timezone.utc)) != "pending":
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)

    identity_email = _normalize_email(current_user.email)
    if not identity_email or identity_email != invitation.target_email:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    user_result = session.execute(
        select(Usuario, RolUsuario.code).join(RolUsuario, RolUsuario.id == Usuario.role_id)
        .where(Usuario.auth_user_id == current_user.id).with_for_update()
    ).one_or_none()
    if user_result is None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    user, role_code = user_result
    if _normalize_email(user.email) != invitation.target_email or role_code != "client":
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    if session.execute(select(Perfil.id).where(Perfil.owner_user_id == user.id)).scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)
    if session.execute(select(Conductor.id).where(Conductor.user_id == user.id).with_for_update()).scalar_one_or_none() is not None:
        raise HTTPException(status_code=400, detail=INVALID_INVITATION)

    driver_role = session.execute(select(RolUsuario).where(RolUsuario.code == "company_driver")).scalar_one_or_none()
    driver_type = session.execute(select(TipoConductor).where(TipoConductor.id == settings.company_driver_type_id)).scalar_one_or_none()
    if driver_role is None or driver_type is None:
        raise HTTPException(status_code=503, detail="Company-linked driver provisioning is not configured.")

    invitation.accepted_at = datetime.now(timezone.utc)
    user.role_id = driver_role.id
    session.add(Conductor(user_id=user.id, employer_profile_id=profile.id, driver_type_id=driver_type.id))
    try:
        session.commit()
    except Exception:
        session.rollback()
        raise
    return InvitationAccepted(user_id=user.id, profile_id=profile.id)
