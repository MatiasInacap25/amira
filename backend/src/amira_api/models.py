"""Relational mapping of the approved Amira ERD.

Python names are English; ``mapped_column`` preserves the Spanish physical
names used by the source diagram. This module defines persistence only and
does not implement marketplace workflows.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Shared SQLAlchemy metadata for Alembic and structural tests."""

    type_annotation_map = {dict[str, Any]: JSONB}


class Region(Base):
    __tablename__ = "Regiones"
    __table_args__ = (
        CheckConstraint("\"Codigo\" ~ '^[0-9]{2}$'", name="ck_region_code_format"),
        CheckConstraint('"Orden" > 0', name="ck_region_order_positive"),
        UniqueConstraint("Nombre", name="uq_regiones_nombre"),
    )

    code: Mapped[str] = mapped_column("Codigo", String(2), primary_key=True)
    name: Mapped[str] = mapped_column("Nombre", String(120), nullable=False)
    order: Mapped[int] = mapped_column("Orden", SmallInteger, nullable=False)

    communes: Mapped[list[Commune]] = relationship(back_populates="region")


class Commune(Base):
    __tablename__ = "Comunas"
    __table_args__ = (
        CheckConstraint("\"Codigo\" ~ '^[0-9]{5}$'", name="ck_commune_code_format"),
        UniqueConstraint("Codigo_Region", "Nombre", name="uq_comunas_region_nombre"),
        Index("ix_comunas_codigo_region", "Codigo_Region"),
    )

    code: Mapped[str] = mapped_column("Codigo", String(5), primary_key=True)
    region_code: Mapped[str] = mapped_column("Codigo_Region", ForeignKey("Regiones.Codigo", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column("Nombre", String(120), nullable=False)

    region: Mapped[Region] = relationship(back_populates="communes")


class Usuario(Base):
    __tablename__ = "Usuario"
    __table_args__ = (
        # Regex CHECKs (RUT, phone) use PostgreSQL's ~ operator and live in migration 20261010_0005.
        Index("uq_usuario_rut", text('"Rut"'), unique=True, postgresql_where=text('"Rut" IS NOT NULL')),
        Index("uq_usuario_correo_normalizado", func.lower(func.btrim(text('"Correo"'))), unique=True),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    auth_user_id: Mapped[UUID] = mapped_column("ID_Auth_Supabase", Uuid(as_uuid=True), nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column("Nombre", String(120), nullable=False)
    last_name: Mapped[str] = mapped_column("Apellido", String(120), nullable=False)
    email: Mapped[str] = mapped_column("Correo", String(320), nullable=False)
    national_id: Mapped[str | None] = mapped_column("Rut", String(16))
    birth_date: Mapped[date | None] = mapped_column("fecha_nacimiento", Date)
    phone: Mapped[str | None] = mapped_column("Telefono", String(32))
    role_id: Mapped[UUID] = mapped_column("ID_Rol", ForeignKey("Rol_Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    registered_at: Mapped[datetime] = mapped_column("Fecha_registro", DateTime(timezone=True), nullable=False, server_default=func.now())

    role: Mapped[RolUsuario] = relationship(back_populates="users")
    profiles: Mapped[list[Perfil]] = relationship(back_populates="owner")
    driver_record: Mapped[Conductor | None] = relationship(back_populates="user", uselist=False)
    identity_verifications: Mapped[list[VerificacionIdentidad]] = relationship(back_populates="user")
    form_requests: Mapped[list[FormularioServicio]] = relationship(back_populates="customer", foreign_keys="FormularioServicio.customer_id")
    messages: Mapped[list[Mensaje]] = relationship(back_populates="sender", foreign_keys="Mensaje.user_id")
    chat_memberships: Mapped[list[ChatParticipante]] = relationship(back_populates="user")
    ratings: Mapped[list[Valoracion]] = relationship(back_populates="author", foreign_keys="Valoracion.user_id")
    claims: Mapped[list[Reclamo]] = relationship(back_populates="customer")


class RolUsuario(Base):
    __tablename__ = "Rol_Usuario"
    __table_args__ = (
        UniqueConstraint("code", name="uq_rol_usuario_code"),
        CheckConstraint("code IN ('client', 'company_owner', 'company_driver', 'independent_driver', 'demo_fixture')", name="ck_rol_usuario_code_allowed"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column("Rol", String(80), nullable=False, unique=True)
    code: Mapped[str] = mapped_column("code", String(64), nullable=False)
    users: Mapped[list[Usuario]] = relationship(back_populates="role")


class TipoConductor(Base):
    __tablename__ = "Tipo_Conductor"

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column("Rol", String(80), nullable=False, unique=True)
    drivers: Mapped[list[Conductor]] = relationship(back_populates="type")


class RolPerfil(Base):
    __tablename__ = "Rol_Perfil"
    __table_args__ = (
        UniqueConstraint("code", name="uq_rol_perfil_code"),
        CheckConstraint("code IN ('company', 'independent_driver', 'demo_fixture')", name="ck_rol_perfil_code_allowed"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column("Rol", String(80), nullable=False, unique=True)
    code: Mapped[str] = mapped_column("code", String(64), nullable=False)
    profiles: Mapped[list[Perfil]] = relationship(back_populates="role")


class Perfil(Base):
    __tablename__ = "Perfil"
    __table_args__ = (
        Index("uq_perfil_rut_empresa", text('"Rut_Empresa"'), unique=True, postgresql_where=text('"Rut_Empresa" IS NOT NULL')),
        CheckConstraint("length(trim(\"Rut_Empresa\")) > 0 OR \"Rut_Empresa\" IS NULL", name="ck_perfil_company_tax_id_nonblank"),
        CheckConstraint("kind IN ('company', 'independent_driver')", name="ck_perfil_kind_allowed"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    owner_user_id: Mapped[UUID] = mapped_column("ID_user", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column("Descripcion", Text)
    name: Mapped[str] = mapped_column("Nombre", String(160), nullable=False)
    logo_storage_key: Mapped[str | None] = mapped_column("url_logo", String(512))
    role_id: Mapped[UUID] = mapped_column("Rol_Perfil", ForeignKey("Rol_Perfil.ID", ondelete="RESTRICT"), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column("Ubicacion", String(200))
    commune_code: Mapped[str | None] = mapped_column("Codigo_Comuna", ForeignKey("Comunas.Codigo", ondelete="RESTRICT"), index=True)
    registered_at: Mapped[datetime] = mapped_column("fecha_registro", DateTime(timezone=True), nullable=False, server_default=func.now())
    company_tax_id: Mapped[str | None] = mapped_column("Rut_Empresa", String(16))
    kind: Mapped[str] = mapped_column("kind", String(32), nullable=False)
    public_activated_at: Mapped[datetime | None] = mapped_column("public_activated_at", DateTime(timezone=True))

    owner: Mapped[Usuario] = relationship(back_populates="profiles")
    role: Mapped[RolPerfil] = relationship(back_populates="profiles")
    drivers: Mapped[list[Conductor]] = relationship(back_populates="employer_profile", foreign_keys="Conductor.employer_profile_id")
    vehicles: Mapped[list[Vehiculo]] = relationship(back_populates="profile")
    services: Mapped[list[Servicio]] = relationship(back_populates="provider_profile", foreign_keys="Servicio.profile_id")
    available_services: Mapped[list[ServicioDisponible]] = relationship(back_populates="profile")
    trips: Mapped[list[Viaje]] = relationship(back_populates="profile")
    payout_accounts: Mapped[list[CuentaDesembolso]] = relationship(back_populates="profile")
    payouts: Mapped[list[Desembolso]] = relationship(back_populates="beneficiary_profile")


class DriverInvitation(Base):
    __tablename__ = "DriverInvitation"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_driver_invitation_token_hash"),
        CheckConstraint("target_email = lower(btrim(target_email))", name="ck_driver_invitation_target_email_normalized"),
        Index("ix_driver_invitation_company_profile_id", "company_profile_id"),
        Index("ix_driver_invitation_expiry", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column("id", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    company_profile_id: Mapped[UUID] = mapped_column("company_profile_id", ForeignKey("Perfil.ID", ondelete="CASCADE"), nullable=False)
    target_email: Mapped[str] = mapped_column("target_email", String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column("token_hash", String(128), nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column("created_by_user_id", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False)
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column("expires_at", DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column("accepted_at", DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column("revoked_at", DateTime(timezone=True))


class DriverInvitationAttempt(Base):
    __tablename__ = "DriverInvitationAttempt"
    __table_args__ = (
        Index("ix_driver_invitation_attempt_identity_created", "auth_user_id", "auth_session_id", "created_at"),
        Index("ix_driver_invitation_attempt_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column("id", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    auth_user_id: Mapped[UUID] = mapped_column("auth_user_id", Uuid(as_uuid=True), nullable=False)
    auth_session_id: Mapped[str] = mapped_column("auth_session_id", String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now())


class EmailFallbackChallenge(Base):
    __tablename__ = "EmailFallbackChallenge"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_email_fallback_attempt_count_nonnegative"),
        Index("ix_email_fallback_user_expiry", "user_id", "expires_at"),
        Index("ix_email_fallback_auth_session_created", "auth_user_id", "auth_session_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column("id", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID | None] = mapped_column("user_id", ForeignKey("Usuario.ID", ondelete="CASCADE"), nullable=True)
    auth_user_id: Mapped[UUID] = mapped_column("auth_user_id", Uuid(as_uuid=True), nullable=False)
    auth_session_id: Mapped[str] = mapped_column("auth_session_id", String(128), nullable=False)
    code_hash: Mapped[str] = mapped_column("code_hash", String(128), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column("activated_at", DateTime(timezone=True))
    proof_hash: Mapped[str | None] = mapped_column("proof_hash", String(128))
    proof_expires_at: Mapped[datetime | None] = mapped_column("proof_expires_at", DateTime(timezone=True))
    proof_consumed_at: Mapped[datetime | None] = mapped_column("proof_consumed_at", DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column("expires_at", DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column("consumed_at", DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column("attempt_count", Integer, nullable=False, server_default=text("0"))


class Conductor(Base):
    __tablename__ = "Conductor"
    __table_args__ = (UniqueConstraint("ID_user", name="uq_conductor_user"),)

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column("ID_user", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False)
    employer_profile_id: Mapped[UUID | None] = mapped_column("ID_perfil", ForeignKey("Perfil.ID", ondelete="RESTRICT"), nullable=True, index=True)
    role_name: Mapped[str | None] = mapped_column("Rol", String(80))
    registered_at: Mapped[datetime] = mapped_column("Fecha_registro", DateTime(timezone=True), nullable=False, server_default=func.now())
    driver_type_id: Mapped[UUID] = mapped_column("Tipo_Conductor", ForeignKey("Tipo_Conductor.ID", ondelete="RESTRICT"), nullable=False, index=True)
    location: Mapped[str | None] = mapped_column("Ubicacion", String(200))
    commune_code: Mapped[str | None] = mapped_column("Codigo_Comuna", ForeignKey("Comunas.Codigo", ondelete="RESTRICT"), index=True)

    user: Mapped[Usuario] = relationship(back_populates="driver_record")
    employer_profile: Mapped[Perfil | None] = relationship(back_populates="drivers", foreign_keys=[employer_profile_id])
    type: Mapped[TipoConductor] = relationship(back_populates="drivers")
    trip_assignments: Mapped[list[ViajeVehiculo]] = relationship(back_populates="driver")
    contracted_services: Mapped[list[Servicio]] = relationship(back_populates="contracted_driver", foreign_keys="Servicio.contracted_driver_id")


class Vehiculo(Base):
    __tablename__ = "Vehiculo"
    __table_args__ = (
        Index("uq_vehiculo_patente_normalizada", func.lower(func.btrim(text('"Patente"'))), unique=True),
        CheckConstraint('"Año" IS NULL OR "Año" BETWEEN 1886 AND 2200', name="ck_vehiculo_year_range"),
        CheckConstraint('"Peso_maximo" IS NULL OR "Peso_maximo" > 0', name="ck_vehiculo_max_weight_positive"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID] = mapped_column("ID_Perfil", ForeignKey("Perfil.ID", ondelete="RESTRICT"), nullable=False, index=True)
    plate: Mapped[str] = mapped_column("Patente", String(16), nullable=False)
    brand: Mapped[str] = mapped_column("Marca", String(80), nullable=False)
    model: Mapped[str] = mapped_column("Modelo", String(100), nullable=False)
    year: Mapped[int | None] = mapped_column("Año", SmallInteger)
    maximum_weight: Mapped[Decimal | None] = mapped_column("Peso_maximo", Numeric(12, 2))
    registered_at: Mapped[datetime] = mapped_column("fecha_registro", DateTime(timezone=True), nullable=False, server_default=func.now())
    image_storage_key: Mapped[str] = mapped_column("Imagen_Storage_Key", String(512), nullable=False)

    profile: Mapped[Perfil] = relationship(back_populates="vehicles")
    trip_assignments: Mapped[list[ViajeVehiculo]] = relationship(back_populates="vehicle")
    services: Mapped[list[Servicio]] = relationship(back_populates="vehicle", foreign_keys="Servicio.vehicle_id")


class TipoServicio(Base):
    __tablename__ = "Tipos_Servicio"
    __table_args__ = (
        UniqueConstraint("Slug", name="uq_tipos_servicio_slug"),
        CheckConstraint("\"Slug\" ~ '^[a-z0-9]+(-[a-z0-9]+)*$'", name="ck_tipos_servicio_slug_format"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column("Nombre_servicio", String(120), nullable=False, unique=True)
    slug: Mapped[str] = mapped_column("Slug", String(120), nullable=False)
    available_profiles: Mapped[list[ServicioDisponible]] = relationship(back_populates="service_type")
    quotations: Mapped[list[Cotizacion]] = relationship(back_populates="service_type")
    form_requests: Mapped[list[FormularioServicio]] = relationship(back_populates="service_type")


class ServicioDisponible(Base):
    __tablename__ = "Servicios_Disponibles"
    __table_args__ = (UniqueConstraint("ID_Perfil", "ID_Tipo_Servicio", name="uq_servicios_disponibles_profile_type"),)

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID] = mapped_column("ID_Perfil", ForeignKey("Perfil.ID", ondelete="CASCADE"), nullable=False, index=True)
    service_type_id: Mapped[UUID] = mapped_column("ID_Tipo_Servicio", ForeignKey("Tipos_Servicio.ID", ondelete="RESTRICT"), nullable=False, index=True)

    profile: Mapped[Perfil] = relationship(back_populates="available_services")
    service_type: Mapped[TipoServicio] = relationship(back_populates="available_profiles")


class FormularioServicio(Base):
    __tablename__ = "Formulario_servicio"
    __table_args__ = (
        CheckConstraint('"Peso_Estimado" IS NULL OR "Peso_Estimado" >= 0', name="ck_form_weight_nonnegative"),
        CheckConstraint('"Volumen_Estimado" IS NULL OR "Volumen_Estimado" >= 0', name="ck_form_volume_nonnegative"),
        CheckConstraint("\"Estado\" IN ('pending', 'accepted', 'rejected')", name="ck_form_status_allowed"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID | None] = mapped_column("ID_Perfil", ForeignKey("Perfil.ID", ondelete="SET NULL"), index=True)
    service_type_id: Mapped[UUID] = mapped_column("Tipo_Servicio", ForeignKey("Tipos_Servicio.ID", ondelete="RESTRICT"), nullable=False, index=True)
    origin: Mapped[str | None] = mapped_column("Origen", String(300))
    destination: Mapped[str | None] = mapped_column("Destino", String(300))
    origin_commune_code: Mapped[str | None] = mapped_column("Codigo_Comuna_Origen", ForeignKey("Comunas.Codigo", ondelete="RESTRICT"), index=True)
    destination_commune_code: Mapped[str | None] = mapped_column("Codigo_Comuna_Destino", ForeignKey("Comunas.Codigo", ondelete="RESTRICT"), index=True)
    estimated_weight: Mapped[Decimal | None] = mapped_column("Peso_Estimado", Numeric(12, 2))
    estimated_volume: Mapped[Decimal | None] = mapped_column("Volumen_Estimado", Numeric(12, 3))
    requested_at: Mapped[datetime | None] = mapped_column("Fecha", DateTime(timezone=True))
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    description: Mapped[str | None] = mapped_column("Descripcion", Text)
    customer_id: Mapped[UUID] = mapped_column("ID_Usuario", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    is_exclusive: Mapped[bool] = mapped_column("es_exclusivo", Boolean, nullable=False, server_default=text("false"))
    requested_trip_id: Mapped[UUID | None] = mapped_column("ID_Viaje", ForeignKey("Viaje.ID", ondelete="SET NULL"), index=True)
    cargo_measurements: Mapped[str | None] = mapped_column("Detalle_Carga_Medidas", Text)

    selected_profile: Mapped[Perfil | None] = relationship(foreign_keys=[profile_id])
    service_type: Mapped[TipoServicio] = relationship(back_populates="form_requests")
    customer: Mapped[Usuario] = relationship(back_populates="form_requests", foreign_keys=[customer_id])
    requested_trip: Mapped[Viaje | None] = relationship(back_populates="form_requests")
    images: Mapped[list[ImagenFormulario]] = relationship(back_populates="form", cascade="all, delete-orphan")
    chats: Mapped[list[Chat]] = relationship(back_populates="form")
    service: Mapped[Servicio | None] = relationship(back_populates="form", uselist=False)


class ImagenFormulario(Base):
    __tablename__ = "Imagenes_Formulario"

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    private_storage_key: Mapped[str] = mapped_column("URL", String(512), nullable=False)
    form_id: Mapped[UUID] = mapped_column("ID_Formulario", ForeignKey("Formulario_servicio.ID", ondelete="CASCADE"), nullable=False, index=True)

    form: Mapped[FormularioServicio] = relationship(back_populates="images")


class Chat(Base):
    __tablename__ = "Chat"

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    created_at: Mapped[datetime] = mapped_column("Fecha_creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    form_id: Mapped[UUID] = mapped_column("ID_Formulario", ForeignKey("Formulario_servicio.ID", ondelete="CASCADE"), nullable=False, index=True)

    form: Mapped[FormularioServicio] = relationship(back_populates="chats")
    participants: Mapped[list[ChatParticipante]] = relationship(back_populates="chat", cascade="all, delete-orphan")
    messages: Mapped[list[Mensaje]] = relationship(back_populates="chat", foreign_keys="Mensaje.chat_id", cascade="all, delete-orphan")
    quotations: Mapped[list[Cotizacion]] = relationship(back_populates="chat")


class ChatParticipante(Base):
    __tablename__ = "Chat_participantes"
    __table_args__ = (
        UniqueConstraint("ID_Chat", "ID_user", name="uq_chat_participants_chat_user"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column("ID_user", ForeignKey("Usuario.ID", ondelete="CASCADE"), nullable=False, index=True)
    chat_id: Mapped[UUID] = mapped_column("ID_Chat", ForeignKey("Chat.ID", ondelete="CASCADE"), nullable=False, index=True)

    user: Mapped[Usuario] = relationship(back_populates="chat_memberships")
    chat: Mapped[Chat] = relationship(back_populates="participants")


class Mensaje(Base):
    __tablename__ = "Mensajes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ID_Chat", "ID_Usuario"],
            ["Chat_participantes.ID_Chat", "Chat_participantes.ID_user"],
            name="fk_message_sender_is_chat_member",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    chat_id: Mapped[UUID] = mapped_column("ID_Chat", ForeignKey("Chat.ID", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column("ID_Usuario", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    content: Mapped[str] = mapped_column("Contenido", Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())

    chat: Mapped[Chat] = relationship(back_populates="messages", foreign_keys=[chat_id])
    sender: Mapped[Usuario] = relationship(back_populates="messages", foreign_keys=[user_id])


class Cotizacion(Base):
    __tablename__ = "Cotizacion"
    __table_args__ = (
        CheckConstraint('"Moneda" = \'CLP\'', name="ck_quote_currency_clp"),
        CheckConstraint('"Valor" >= 0', name="ck_quote_amount_nonnegative"),
        CheckConstraint(
            "\"Estado\" IN ('pending', 'paid', 'rejected', 'expired', 'superseded')",
            name="ck_quote_status_allowed",
        ),
        CheckConstraint('"Fecha_Vencimiento" IS NULL OR "Fecha_Vencimiento" > "Fecha_Creacion"', name="ck_quote_expiry_after_creation"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    chat_id: Mapped[UUID] = mapped_column("ID_Chat", ForeignKey("Chat.ID", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    amount: Mapped[Decimal] = mapped_column("Valor", Numeric(18, 4), nullable=False)
    origin: Mapped[str] = mapped_column("Origen", String(300), nullable=False)
    destination: Mapped[str] = mapped_column("Destino", String(300), nullable=False)
    service_at: Mapped[datetime | None] = mapped_column("Fecha", DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column("Descripcion", Text)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    service_type_id: Mapped[UUID] = mapped_column("Tipo_Servicio", ForeignKey("Tipos_Servicio.ID", ondelete="RESTRICT"), nullable=False, index=True)
    expires_at: Mapped[datetime | None] = mapped_column("Fecha_Vencimiento", DateTime(timezone=True))
    is_exclusive: Mapped[bool] = mapped_column("es_exclusivo", Boolean, nullable=False, server_default=text("false"))
    currency: Mapped[str] = mapped_column("Moneda", String(3), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column("Fecha_Aceptacion", DateTime(timezone=True))
    agreed_terms: Mapped[dict[str, Any] | None] = mapped_column("Condiciones_Acordadas", JSONB)

    chat: Mapped[Chat] = relationship(back_populates="quotations")
    service_type: Mapped[TipoServicio] = relationship(back_populates="quotations")
    payments: Mapped[list[Pago]] = relationship(back_populates="quotation")
    accepted_service: Mapped[Servicio | None] = relationship(back_populates="accepted_quotation", foreign_keys="Servicio.accepted_quotation_id", uselist=False)


class Servicio(Base):
    __tablename__ = "Servicio"
    __table_args__ = (
        UniqueConstraint("ID_Formulario", name="uq_service_form"),
        UniqueConstraint("ID", "ID_Cotizacion_Aceptada", name="uq_service_id_accepted_quote"),
        CheckConstraint('"Valor" IS NULL OR "Valor" >= 0', name="ck_service_amount_nonnegative"),
        CheckConstraint(
            '("ID_Viaje" IS NULL AND "ID_Vehiculo" IS NULL) OR ("ID_Viaje" IS NOT NULL AND "ID_Vehiculo" IS NOT NULL)',
            name="ck_service_trip_vehicle_pair",
        ),
        CheckConstraint(
            '("ID_Viaje" IS NULL AND "ID_Parada_Retiro" IS NULL AND "ID_Parada_Entrega" IS NULL) OR '
            '("ID_Viaje" IS NOT NULL AND "ID_Parada_Retiro" IS NOT NULL AND "ID_Parada_Entrega" IS NOT NULL)',
            name="ck_service_trip_stops_pair",
        ),
        ForeignKeyConstraint(
            ["ID_Viaje", "ID_Vehiculo"],
            ["Viaje_Vehiculo.ID_Viaje", "Viaje_Vehiculo.ID_Vehiculo"],
            name="fk_service_trip_vehicle_assignment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ID_Viaje", "ID_Parada_Retiro"],
            ["Parada_Viaje.ID_Viaje", "Parada_Viaje.ID"],
            name="fk_service_pickup_stop_same_trip",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["ID_Viaje", "ID_Parada_Entrega"],
            ["Parada_Viaje.ID_Viaje", "Parada_Viaje.ID"],
            name="fk_service_delivery_stop_same_trip",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID] = mapped_column("ID_Perfil", ForeignKey("Perfil.ID", ondelete="RESTRICT"), nullable=False, index=True)
    customer_id: Mapped[UUID] = mapped_column("ID_Cliente", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    is_exclusive: Mapped[bool] = mapped_column("es_exclusivo", Boolean, nullable=False, server_default=text("false"))
    is_published: Mapped[bool | None] = mapped_column("puclicado", Boolean)
    service_at: Mapped[datetime | None] = mapped_column("Fecha", DateTime(timezone=True))
    description: Mapped[str | None] = mapped_column("Descripcion", Text)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    amount: Mapped[Decimal | None] = mapped_column("Valor", Numeric(18, 4))
    contracted_driver_id: Mapped[UUID | None] = mapped_column("ID_Conductor", ForeignKey("Conductor.ID", ondelete="SET NULL"), index=True)
    starts_at: Mapped[datetime | None] = mapped_column("Fecha_Inicio", DateTime(timezone=True))
    vehicle_id: Mapped[UUID | None] = mapped_column("ID_Vehiculo", ForeignKey("Vehiculo.ID", ondelete="RESTRICT"))
    trip_id: Mapped[UUID | None] = mapped_column("ID_Viaje", ForeignKey("Viaje.ID", ondelete="RESTRICT"))
    pickup_stop_id: Mapped[UUID | None] = mapped_column("ID_Parada_Retiro", Uuid(as_uuid=True))
    delivery_stop_id: Mapped[UUID | None] = mapped_column("ID_Parada_Entrega", Uuid(as_uuid=True))
    form_id: Mapped[UUID] = mapped_column("ID_Formulario", ForeignKey("Formulario_servicio.ID", ondelete="RESTRICT"), nullable=False)
    accepted_quotation_id: Mapped[UUID] = mapped_column("ID_Cotizacion_Aceptada", ForeignKey("Cotizacion.ID", ondelete="RESTRICT"), nullable=False, unique=True)
    capacity_validated_at: Mapped[datetime | None] = mapped_column("Capacidad_Validada_En", DateTime(timezone=True))
    payment_confirmed_at: Mapped[datetime | None] = mapped_column("Fecha_Pago_Confirmado", DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column("Fecha_Finalizacion", DateTime(timezone=True))
    completion_notified_at: Mapped[datetime | None] = mapped_column("Fecha_Notificacion_Finalizacion", DateTime(timezone=True))
    customer_consent_at: Mapped[datetime | None] = mapped_column("Fecha_Conformidad_Cliente", DateTime(timezone=True))
    payout_deadline_at: Mapped[datetime | None] = mapped_column("Fecha_Limite_Liberacion", DateTime(timezone=True))
    delivery_evidence_key: Mapped[str | None] = mapped_column("Referencia_Entrega_Privada", String(512))

    provider_profile: Mapped[Perfil] = relationship(back_populates="services", foreign_keys=[profile_id])
    customer: Mapped[Usuario] = relationship(foreign_keys=[customer_id])
    contracted_driver: Mapped[Conductor | None] = relationship(back_populates="contracted_services", foreign_keys=[contracted_driver_id])
    vehicle: Mapped[Vehiculo | None] = relationship(back_populates="services", foreign_keys=[vehicle_id])
    trip: Mapped[Viaje | None] = relationship(back_populates="services", foreign_keys=[trip_id])
    pickup_stop: Mapped[ParadaViaje | None] = relationship(foreign_keys=[trip_id, pickup_stop_id], viewonly=True)
    delivery_stop: Mapped[ParadaViaje | None] = relationship(foreign_keys=[trip_id, delivery_stop_id], viewonly=True)
    form: Mapped[FormularioServicio] = relationship(back_populates="service")
    accepted_quotation: Mapped[Cotizacion] = relationship(back_populates="accepted_service", foreign_keys=[accepted_quotation_id])
    rating: Mapped[Valoracion | None] = relationship(back_populates="service", uselist=False)
    claims: Mapped[list[Reclamo]] = relationship(back_populates="service")
    payouts: Mapped[list[Desembolso]] = relationship(back_populates="service")


class Viaje(Base):
    __tablename__ = "Viaje"

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID] = mapped_column("ID_Perfil", ForeignKey("Perfil.ID", ondelete="RESTRICT"), nullable=False, index=True)
    registered_at: Mapped[datetime] = mapped_column("Fecha_registro", DateTime(timezone=True), nullable=False, server_default=func.now())
    origin: Mapped[str] = mapped_column("Origen", String(300), nullable=False)
    destination: Mapped[str] = mapped_column("Destino", String(300), nullable=False)
    origin_commune_code: Mapped[str | None] = mapped_column("Codigo_Comuna_Origen", ForeignKey("Comunas.Codigo", ondelete="RESTRICT"), index=True)
    destination_commune_code: Mapped[str | None] = mapped_column("Codigo_Comuna_Destino", ForeignKey("Comunas.Codigo", ondelete="RESTRICT"), index=True)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    departure_at: Mapped[datetime | None] = mapped_column("Fecha_Salida", DateTime(timezone=True))
    is_published: Mapped[bool] = mapped_column("Publicado", Boolean, nullable=False, server_default=text("false"))
    accepts_requests: Mapped[bool] = mapped_column("Acepta_Solicitudes", Boolean, nullable=False, server_default=text("false"))

    profile: Mapped[Perfil] = relationship(back_populates="trips")
    form_requests: Mapped[list[FormularioServicio]] = relationship(back_populates="requested_trip")
    vehicle_assignments: Mapped[list[ViajeVehiculo]] = relationship(back_populates="trip", cascade="all, delete-orphan")
    stops: Mapped[list[ParadaViaje]] = relationship(back_populates="trip", cascade="all, delete-orphan", order_by="ParadaViaje.order")
    services: Mapped[list[Servicio]] = relationship(back_populates="trip", foreign_keys="Servicio.trip_id")


class ViajeVehiculo(Base):
    __tablename__ = "Viaje_Vehiculo"

    trip_id: Mapped[UUID] = mapped_column("ID_Viaje", ForeignKey("Viaje.ID", ondelete="CASCADE"), primary_key=True)
    vehicle_id: Mapped[UUID] = mapped_column("ID_Vehiculo", ForeignKey("Vehiculo.ID", ondelete="RESTRICT"), primary_key=True)
    driver_id: Mapped[UUID] = mapped_column("ID_Conductor", ForeignKey("Conductor.ID", ondelete="RESTRICT"), nullable=False, index=True)

    trip: Mapped[Viaje] = relationship(back_populates="vehicle_assignments")
    vehicle: Mapped[Vehiculo] = relationship(back_populates="trip_assignments")
    driver: Mapped[Conductor] = relationship(back_populates="trip_assignments")


class ParadaViaje(Base):
    __tablename__ = "Parada_Viaje"
    __table_args__ = (
        UniqueConstraint("ID_Viaje", "Orden", name="uq_trip_stop_order"),
        UniqueConstraint("ID_Viaje", "ID", name="uq_trip_stop_trip_id"),
        CheckConstraint('"Orden" > 0', name="ck_trip_stop_order_positive"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    trip_id: Mapped[UUID] = mapped_column("ID_Viaje", ForeignKey("Viaje.ID", ondelete="CASCADE"), nullable=False, index=True)
    order: Mapped[int] = mapped_column("Orden", Integer, nullable=False)
    address: Mapped[str] = mapped_column("Direccion", String(300), nullable=False)
    estimated_at: Mapped[datetime | None] = mapped_column("Fecha_Hora_Estimada", DateTime(timezone=True))
    status: Mapped[str | None] = mapped_column("Estado", String(40))

    trip: Mapped[Viaje] = relationship(back_populates="stops")


class Pago(Base):
    __tablename__ = "Pago"
    __table_args__ = (
        CheckConstraint('"Moneda" = \'CLP\'', name="ck_payment_currency_clp"),
        UniqueConstraint("ID", "ID_Cotizacion", name="uq_payment_id_quote"),
        UniqueConstraint("Proveedor", "ID_Pago_Proveedor", name="uq_payment_provider_external_id"),
        UniqueConstraint("Proveedor", "Clave_Idempotencia", name="uq_payment_provider_idempotency_key"),
        CheckConstraint('"Monto" >= 0', name="ck_payment_amount_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    quotation_id: Mapped[UUID] = mapped_column("ID_Cotizacion", ForeignKey("Cotizacion.ID", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column("Proveedor", String(80), nullable=False)
    provider_payment_id: Mapped[str] = mapped_column("ID_Pago_Proveedor", String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column("Clave_Idempotencia", String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column("Monto", Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column("Moneda", String(3), nullable=False)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("Fecha_Actualizacion", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column("Fecha_Confirmacion", DateTime(timezone=True))

    quotation: Mapped[Cotizacion] = relationship(back_populates="payments")
    refunds: Mapped[list[Reembolso]] = relationship(back_populates="payment")
    payouts: Mapped[list[Desembolso]] = relationship(back_populates="payment")


class Reembolso(Base):
    __tablename__ = "Reembolso"
    __table_args__ = (
        CheckConstraint('"Moneda" = \'CLP\'', name="ck_refund_currency_clp"),
        UniqueConstraint("Proveedor", "ID_Reembolso_Proveedor", name="uq_refund_provider_external_id"),
        UniqueConstraint("Proveedor", "Clave_Idempotencia", name="uq_refund_provider_idempotency_key"),
        CheckConstraint('"Monto" > 0', name="ck_refund_amount_positive"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    payment_id: Mapped[UUID] = mapped_column("ID_Pago", ForeignKey("Pago.ID", ondelete="RESTRICT"), nullable=False, index=True)
    claim_id: Mapped[UUID | None] = mapped_column("ID_Reclamo", ForeignKey("Reclamo.ID", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column("Proveedor", String(80), nullable=False)
    provider_refund_id: Mapped[str] = mapped_column("ID_Reembolso_Proveedor", String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column("Clave_Idempotencia", String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column("Monto", Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column("Moneda", String(3), nullable=False)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("Fecha_Actualizacion", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    confirmed_at: Mapped[datetime | None] = mapped_column("Fecha_Confirmacion", DateTime(timezone=True))

    payment: Mapped[Pago] = relationship(back_populates="refunds")
    claim: Mapped[Reclamo | None] = relationship(back_populates="refunds")


class Reclamo(Base):
    __tablename__ = "Reclamo"

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    service_id: Mapped[UUID] = mapped_column("ID_Servicio", ForeignKey("Servicio.ID", ondelete="RESTRICT"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column("ID_Usuario", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column("Motivo", Text, nullable=False)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column("Fecha_Resolucion", DateTime(timezone=True))
    resolution: Mapped[str | None] = mapped_column("Resolucion", Text)
    private_evidence_key: Mapped[str | None] = mapped_column("Referencia_Evidencia_Privada", String(512))

    service: Mapped[Servicio] = relationship(back_populates="claims")
    customer: Mapped[Usuario] = relationship(back_populates="claims")
    refunds: Mapped[list[Reembolso]] = relationship(back_populates="claim")


class Valoracion(Base):
    __tablename__ = "Valoracion"
    __table_args__ = (
        UniqueConstraint("ID_Servicio", name="uq_rating_service"),
        CheckConstraint('"Rating" BETWEEN 1 AND 5', name="ck_rating_range"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    service_id: Mapped[UUID] = mapped_column("ID_Servicio", ForeignKey("Servicio.ID", ondelete="RESTRICT"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column("ID_Usuario", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    rating: Mapped[int] = mapped_column("Rating", SmallInteger, nullable=False)
    comment: Mapped[str | None] = mapped_column("Comentario", Text)
    created_at: Mapped[datetime] = mapped_column("Fecha_Registro", DateTime(timezone=True), nullable=False, server_default=func.now())

    service: Mapped[Servicio] = relationship(back_populates="rating")
    author: Mapped[Usuario] = relationship(back_populates="ratings", foreign_keys=[user_id])


class VerificacionIdentidad(Base):
    __tablename__ = "Verificacion_Identidad"
    __table_args__ = (UniqueConstraint("Proveedor", "ID_Verificacion_Proveedor", name="uq_identity_provider_verification"),)

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[UUID] = mapped_column("ID_Usuario", ForeignKey("Usuario.ID", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column("Proveedor", String(80), nullable=False)
    provider_verification_id: Mapped[str] = mapped_column("ID_Verificacion_Proveedor", String(200), nullable=False)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("Fecha_Actualizacion", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    verified_at: Mapped[datetime | None] = mapped_column("Fecha_Verificacion", DateTime(timezone=True))
    rejection_reason: Mapped[str | None] = mapped_column("Motivo_Rechazo", Text)

    user: Mapped[Usuario] = relationship(back_populates="identity_verifications")


class CuentaDesembolso(Base):
    __tablename__ = "Cuenta_Desembolso"
    __table_args__ = (
        UniqueConstraint("Proveedor", "ID_Cuenta_Proveedor", name="uq_payout_account_provider_reference"),
        Index("ix_payout_account_profile_status", "ID_Perfil", "Estado_Registro"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID] = mapped_column("ID_Perfil", ForeignKey("Perfil.ID", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column("Proveedor", String(80), nullable=False)
    provider_account_id: Mapped[str] = mapped_column("ID_Cuenta_Proveedor", String(200), nullable=False)
    registration_status: Mapped[str] = mapped_column("Estado_Registro", String(40), nullable=False)
    payouts_enabled: Mapped[bool] = mapped_column("Habilitada_Desembolsos", Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("Fecha_Actualizacion", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    profile: Mapped[Perfil] = relationship(back_populates="payout_accounts")
    payouts: Mapped[list[Desembolso]] = relationship(back_populates="payout_account")


class Desembolso(Base):
    __tablename__ = "Desembolso"
    __table_args__ = (
        CheckConstraint('"Moneda" = \'CLP\'', name="ck_payout_currency_clp"),
        UniqueConstraint("Proveedor", "ID_Desembolso_Proveedor", name="uq_payout_provider_external_id"),
        UniqueConstraint("Proveedor", "Clave_Idempotencia", name="uq_payout_provider_idempotency_key"),
        CheckConstraint('"Monto_Neto" >= 0', name="ck_payout_net_amount_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column("ID", Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    payment_id: Mapped[UUID] = mapped_column("ID_Pago", ForeignKey("Pago.ID", ondelete="RESTRICT"), nullable=False, index=True)
    service_id: Mapped[UUID] = mapped_column("ID_Servicio", ForeignKey("Servicio.ID", ondelete="RESTRICT"), nullable=False, index=True)
    beneficiary_profile_id: Mapped[UUID] = mapped_column("ID_Perfil_Beneficiario", ForeignKey("Perfil.ID", ondelete="RESTRICT"), nullable=False, index=True)
    payout_account_id: Mapped[UUID] = mapped_column("ID_Cuenta_Desembolso", ForeignKey("Cuenta_Desembolso.ID", ondelete="RESTRICT"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column("Proveedor", String(80), nullable=False)
    provider_payout_id: Mapped[str] = mapped_column("ID_Desembolso_Proveedor", String(200), nullable=False)
    idempotency_key: Mapped[str] = mapped_column("Clave_Idempotencia", String(200), nullable=False)
    net_amount: Mapped[Decimal] = mapped_column("Monto_Neto", Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column("Moneda", String(3), nullable=False)
    status: Mapped[str] = mapped_column("Estado", String(40), nullable=False)
    created_at: Mapped[datetime] = mapped_column("Fecha_Creacion", DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column("Fecha_Actualizacion", DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    requested_at: Mapped[datetime | None] = mapped_column("Fecha_Solicitud", DateTime(timezone=True))
    confirmed_at: Mapped[datetime | None] = mapped_column("Fecha_Confirmacion", DateTime(timezone=True))

    payment: Mapped[Pago] = relationship(back_populates="payouts")
    service: Mapped[Servicio] = relationship(back_populates="payouts")
    beneficiary_profile: Mapped[Perfil] = relationship(back_populates="payouts")
    payout_account: Mapped[CuentaDesembolso] = relationship(back_populates="payouts")
