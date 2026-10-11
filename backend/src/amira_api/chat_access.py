"""Chat participation rules shared by the chat, quotation and payment routes.

A caller may act on a chat only when their Usuario is a participant. A missing chat and a chat the caller
does not participate in must produce the same result, so callers use these helpers and answer 404 for both.
"""

from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, aliased

from amira_api.auth import AuthenticatedUser
from amira_api.models import Chat, ChatParticipante, Commune, FormularioServicio, Perfil, TipoServicio, Usuario


def caller_account(session: Session, current_user: AuthenticatedUser):
    """The caller's Usuario id and display name, or None when the auth identity has no account."""
    return session.execute(
        select(Usuario.id, Usuario.first_name, Usuario.last_name).where(Usuario.auth_user_id == current_user.id)
    ).one_or_none()


def caller_chats(caller_id: UUID) -> Select:
    """Chats the caller participates in, one row per chat.

    Every chat in this relation has an accepted request with a provider profile (the accept route
    always creates both), so the profile join is inner. Counts and items both build from this relation.
    """
    origin_commune = aliased(Commune)
    destination_commune = aliased(Commune)
    customer = aliased(Usuario)
    return (
        select(
            Chat.id.label("chat_id"),
            Chat.created_at.label("created_at"),
            FormularioServicio.id.label("request_id"),
            FormularioServicio.customer_id.label("customer_id"),
            FormularioServicio.origin.label("origin_text"),
            FormularioServicio.destination.label("destination_text"),
            TipoServicio.id.label("service_type_id"),
            TipoServicio.name.label("service_name"),
            origin_commune.name.label("origin_commune_name"),
            destination_commune.name.label("destination_commune_name"),
            Perfil.id.label("provider_profile_id"),
            Perfil.name.label("provider_name"),
            Perfil.kind.label("provider_kind"),
            customer.first_name.label("customer_first_name"),
            customer.last_name.label("customer_last_name"),
        )
        .select_from(Chat)
        .join(ChatParticipante, ChatParticipante.chat_id == Chat.id)
        .join(FormularioServicio, FormularioServicio.id == Chat.form_id)
        .join(TipoServicio, TipoServicio.id == FormularioServicio.service_type_id)
        .join(Perfil, Perfil.id == FormularioServicio.profile_id)
        .join(customer, customer.id == FormularioServicio.customer_id)
        .outerjoin(origin_commune, origin_commune.code == FormularioServicio.origin_commune_code)
        .outerjoin(destination_commune, destination_commune.code == FormularioServicio.destination_commune_code)
        .where(ChatParticipante.user_id == caller_id)
    )
