"""Payment routes and the composition root for the PaymentProvider port.

This module is the only place that chooses an adapter. The simulated adapter is enabled only when APP_ENV is set
explicitly to a development value; otherwise the payment endpoints answer 503 and the simulated endpoints answer 404.
"""

import hmac
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from amira_api.auth import AuthenticatedUser, get_current_user
from amira_api.chat_access import caller_account, caller_chats
from amira_api.clock import utc_now
from amira_api.db import get_db_session
from amira_api.models import Chat, Cotizacion, Pago, Servicio, PaymentProviderTransaction
from amira_api.payment_provider import SIMULATED_PROVIDER_NAME, PaymentProvider
from amira_api.mercado_pago_provider import MercadoPagoError, MercadoPagoProvider, verify_webhook_signature
from amira_api.payment_schemas import (
    PaymentCheckout,
    PaymentConfirmationRequest,
    PaymentDetail,
    PaymentResult,
    SimulatedPaymentCompletion,
)
from amira_api.payment_service import (
    ConfirmationRefused,
    PaymentConflict,
    PaymentNotFound,
    confirm_payment,
    consume_checkout_token,
    start_payment,
)
from amira_api.quotation_service import effective_status
from amira_api.settings import Settings, get_settings
from amira_api.simulated_payment_provider import SIMULATOR_APP_ENVS, SimulatedPaymentProvider

router = APIRouter(prefix="/api", tags=["payments"])
CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
Database = Annotated[Session, Depends(get_db_session)]
AppSettings = Annotated[Settings, Depends(get_settings)]
WEBHOOK_SECRET_HEADER = "X-Amira-Payment-Webhook-Secret"
PAYMENTS_NOT_CONFIGURED = "Payments are not configured."
CONFIRMATION_REFUSED = "La firma de la confirmación no es válida."


def _simulator_enabled(settings: Settings) -> bool:
    # Fail closed, mirroring DEV_SKIP_SMS_MFA: APP_ENV must be set explicitly to an allowlisted value.
    return "app_env" in settings.model_fields_set and settings.app_env.strip().lower() in SIMULATOR_APP_ENVS


def _simulated_provider(settings: Settings, *, not_found_outside_dev: bool) -> SimulatedPaymentProvider:
    if not _simulator_enabled(settings):
        if not_found_outside_dev:
            raise HTTPException(status_code=404, detail="Not found.")
        raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
    secret = settings.payment_simulator_secret.get_secret_value() if settings.payment_simulator_secret else ""
    if not secret or not settings.frontend_base_url:
        raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
    return SimulatedPaymentProvider(
        secret=secret,
        frontend_base_url=settings.frontend_base_url,
        app_env=settings.app_env,
    )


def get_payment_provider(settings: AppSettings) -> PaymentProvider:
    """Choose an explicitly configured provider, failing closed for missing credentials."""
    if settings.payment_provider == "mercado_pago":
        token = settings.mercado_pago_access_token.get_secret_value() if settings.mercado_pago_access_token else ""
        if not token or not settings.frontend_base_url or not settings.mercado_pago_test_seller_id:
            raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
        return MercadoPagoProvider(access_token=token, frontend_base_url=settings.frontend_base_url,
                                   test_seller_id=settings.mercado_pago_test_seller_id)
    if settings.payment_provider != "simulated":
        raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
    return _simulated_provider(settings, not_found_outside_dev=False)


def get_simulated_provider(settings: AppSettings) -> SimulatedPaymentProvider:
    """The simulated checkout endpoints do not exist outside development."""
    return _simulated_provider(settings, not_found_outside_dev=True)


def require_webhook_secret(
    settings: AppSettings,
    supplied: Annotated[str | None, Header(alias=WEBHOOK_SECRET_HEADER)] = None,
) -> None:
    """Server-to-server authentication for confirmations. Fails closed when the secret is not configured."""
    configured = settings.payment_webhook_secret.get_secret_value() if settings.payment_webhook_secret else ""
    if not configured:
        raise HTTPException(status_code=503, detail="Payment webhooks are not configured.")
    if supplied is None or not hmac.compare_digest(supplied.encode("utf-8"), configured.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Secreto de webhook no válido.")


def _caller_quotation(session: Session, current_user: AuthenticatedUser, quotation_id: UUID):
    account = caller_account(session, current_user)
    quotation = session.get(Cotizacion, quotation_id) if account is not None else None
    row = None
    if quotation is not None:
        row = session.execute(caller_chats(account.id).where(Chat.id == quotation.chat_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Quotation not found.")
    return account.id, quotation, row


def _caller_payment(session: Session, current_user: AuthenticatedUser, payment_id: UUID):
    account = caller_account(session, current_user)
    payment = session.get(Pago, payment_id) if account is not None else None
    quotation = session.get(Cotizacion, payment.quotation_id) if payment is not None else None
    row = None
    if quotation is not None:
        row = session.execute(caller_chats(account.id).where(Chat.id == quotation.chat_id)).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Payment not found.")
    return account.id, payment, quotation, row


def _payment_status(session: Session, payment: Pago, service_id) -> str:
    if payment.provider == "mercado_pago" and payment.status == "approved":
        count = session.scalar(select(func.count()).select_from(PaymentProviderTransaction).where(
            PaymentProviderTransaction.payment_id == payment.id))
        if service_id is None or count > 1:
            return "review"
    return payment.status


def _reconcile(session: Session, provider: MercadoPagoProvider, payment: Pago, transaction_evidence: list[tuple[str, str]]) -> Pago:
    for transaction_id, status in transaction_evidence:
        payment = session.execute(select(Pago).where(Pago.id == payment.id).with_for_update()).scalar_one()
        if status == "rejected":
            if payment.status == "pending":
                payment = confirm_payment(session, provider, payment_id=payment.id, provider_payment_id=payment.provider_payment_id,
                                          status=status, signature="", now=utc_now(), verified=True)
            continue
        existing = session.get(PaymentProviderTransaction, transaction_id)
        if existing is not None:
            if existing.payment_id != payment.id:
                raise PaymentConflict("La transacción corresponde a otro pago.")
            continue
        session.add(PaymentProviderTransaction(provider_transaction_id=transaction_id, payment_id=payment.id, created_at=utc_now()))
        session.flush()
        payment = confirm_payment(session, provider, payment_id=payment.id, provider_payment_id=payment.provider_payment_id,
                                  status="approved", signature="", now=utc_now(), verified=True,
                                  provider_transaction_id=transaction_id)
        session.commit()
    return payment


def _result(session: Session, payment: Pago) -> PaymentResult:
    quotation = session.get(Cotizacion, payment.quotation_id)
    service_id = session.query(Servicio.id).filter(Servicio.accepted_quotation_id == quotation.id).scalar()
    return PaymentResult(
        payment_id=payment.id,
        status=_payment_status(session, payment, service_id),
        quotation_id=quotation.id,
        quotation_status=effective_status(quotation, utc_now()),
        service_id=service_id,
    )


def _apply_confirmation(
    session: Session,
    provider: PaymentProvider,
    *,
    payment_id: UUID,
    provider_payment_id: str,
    status: str,
    signature: str,
) -> PaymentResult:
    try:
        payment = confirm_payment(
            session,
            provider,
            payment_id=payment_id,
            provider_payment_id=provider_payment_id,
            status=status,
            signature=signature,
            now=utc_now(),
        )
    except ConfirmationRefused:
        raise HTTPException(status_code=400, detail=CONFIRMATION_REFUSED) from None
    except PaymentNotFound:
        raise HTTPException(status_code=404, detail="Payment not found.") from None
    except PaymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return _result(session, payment)


@router.post("/quotations/{quotation_id}/payments", response_model=PaymentCheckout, status_code=201)
def start_quotation_payment(
    quotation_id: UUID,
    current_user: CurrentUser,
    session: Database,
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
) -> PaymentCheckout:
    caller_id, quotation, row = _caller_quotation(session, current_user, quotation_id)
    if row["customer_id"] != caller_id:
        raise HTTPException(status_code=403, detail="Solo el cliente puede pagar esta cotización.")
    try:
        payment, checkout_url = start_payment(session, provider, quotation.id, utc_now())
    except PaymentConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    except MercadoPagoError:
        session.rollback()
        raise HTTPException(status_code=503, detail="Payment provider unavailable.") from None
    return PaymentCheckout(payment_id=payment.id, checkout_url=checkout_url)


@router.post(
    "/payments/confirm",
    response_model=PaymentResult,
    dependencies=[Depends(require_webhook_secret)],
)
def confirm_payment_route(
    payload: PaymentConfirmationRequest,
    session: Database,
    provider: Annotated[PaymentProvider, Depends(get_payment_provider)],
) -> PaymentResult:
    """Server-to-server confirmation from a real provider. Browser sessions never reach this route."""
    if provider.name in (SIMULATED_PROVIDER_NAME, "mercado_pago"):
        raise HTTPException(status_code=403, detail="Las confirmaciones simuladas no pasan por el webhook.")
    return _apply_confirmation(
        session,
        provider,
        payment_id=payload.payment_id,
        provider_payment_id=payload.provider_payment_id,
        status=payload.status,
        signature=payload.signature,
    )


@router.post("/payments/simulated/{payment_id}/complete", response_model=PaymentResult)
def complete_simulated_payment(
    payment_id: UUID,
    payload: SimulatedPaymentCompletion,
    current_user: CurrentUser,
    session: Database,
    provider: Annotated[SimulatedPaymentProvider, Depends(get_simulated_provider)],
) -> PaymentResult:
    caller_id, payment, quotation, row = _caller_payment(session, current_user, payment_id)
    customer_id = row["customer_id"]
    if customer_id != caller_id or payment.provider != SIMULATED_PROVIDER_NAME:
        raise HTTPException(status_code=404, detail="Payment not found.")
    if not provider.verify_checkout_token(payment.id, payment.provider_payment_id, customer_id, payload.token):
        raise HTTPException(status_code=400, detail="El enlace de pago no es válido o expiró.")

    status = "approved" if payload.approve else "rejected"
    if payment.checkout_used_at is not None and payment.status == status:
        # A retry of a decision already applied to this payment returns the stored result.
        return _result(session, payment)
    try:
        # The link is consumed in the same transaction as the confirmation, so a refused confirmation releases it.
        if not consume_checkout_token(session, payment.id, utc_now()):
            raise HTTPException(status_code=400, detail="El enlace de pago ya fue usado.")
        # The server signs the simulated result and runs the same confirmation path as the webhook.
        result = _apply_confirmation(
            session,
            provider,
            payment_id=payment.id,
            provider_payment_id=payment.provider_payment_id,
            status=status,
            signature=provider.sign_confirmation(payment.id, payment.provider_payment_id, status),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return result


@router.get("/payments/{payment_id}", response_model=PaymentDetail)
def read_payment(payment_id: UUID, current_user: CurrentUser, session: Database,
                 settings: AppSettings) -> PaymentDetail:
    caller_id, payment, quotation, row = _caller_payment(session, current_user, payment_id)
    if row["customer_id"] != caller_id:
        raise HTTPException(status_code=403, detail="Solo el cliente puede consultar este pago.")
    if payment.provider == "mercado_pago":
        provider = get_payment_provider(settings)
        if provider.name != "mercado_pago":
            raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
        try:
            transaction_ids = provider.lookup(payment.id, payment.amount, payment.currency)
            payment = _reconcile(session, provider, payment, transaction_ids)
        except MercadoPagoError:
            raise HTTPException(status_code=503, detail="Payment provider unavailable.") from None
    service_id = session.query(Servicio.id).filter(Servicio.accepted_quotation_id == quotation.id).scalar()
    return PaymentDetail(
        payment_id=payment.id,
        status=_payment_status(session, payment, service_id),
        quotation_id=quotation.id,
        quotation_status=effective_status(quotation, utc_now()),
        chat_id=quotation.chat_id,
    )


@router.post("/payments/mercado-pago/webhook", status_code=200)
def mercado_pago_webhook(request: Request, session: Database, settings: AppSettings):
    secret = settings.mercado_pago_webhook_secret.get_secret_value() if settings.mercado_pago_webhook_secret else ""
    if not secret:
        raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
    resource_id = request.query_params.get("data.id", "")
    if not verify_webhook_signature(secret, resource_id, request.headers.get("x-request-id", ""),
                                    request.headers.get("x-signature", "")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature.")
    provider = get_payment_provider(settings)
    if provider.name != "mercado_pago":
        raise HTTPException(status_code=503, detail=PAYMENTS_NOT_CONFIGURED)
    try:
        evidence = provider._request("GET", f"/v1/payments/{resource_id}")
        try:
            payment_id = UUID(str(evidence.get("external_reference")))
        except ValueError:
            return {"ok": True}
        payment = session.get(Pago, payment_id)
        if payment is None or payment.provider != "mercado_pago":
            return {"ok": True}
        transaction_ids = provider.lookup(payment.id, payment.amount, payment.currency, resource_id)
        _reconcile(session, provider, payment, transaction_ids)
    except MercadoPagoError:
        raise HTTPException(status_code=503, detail="Payment provider unavailable.") from None
    except PaymentConflict:
        raise HTTPException(status_code=409, detail="Payment could not be reconciled.") from None
    return {"ok": True}
