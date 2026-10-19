import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amira_api.account_routes import router as account_router
from amira_api.chat_routes import router as chat_router
from amira_api.customer_routes import router as customer_router
from amira_api.fallback_routes import router as fallback_router
from amira_api.invitation_routes import router as invitation_router
from amira_api.location_routes import router as location_router
from amira_api.provider_service_routes import router as provider_service_router
from amira_api.public_routes import router as public_router
from amira_api.payment_routes import router as payment_router
from amira_api.quotation_routes import router as quotation_router
from amira_api.realtime import chat_broker, start_chat_listener
from amira_api.realtime_routes import router as realtime_router
from amira_api.settings import get_settings, warn_if_dev_sms_mfa_bypass_active

settings = get_settings()
warn_if_dev_sms_mfa_bypass_active(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    listener = start_chat_listener(chat_broker, settings)
    try:
        yield
    finally:
        if listener is not None:
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(account_router)
app.include_router(chat_router)
app.include_router(realtime_router)
app.include_router(customer_router)
app.include_router(fallback_router)
app.include_router(invitation_router)
app.include_router(location_router)
app.include_router(provider_service_router)
app.include_router(public_router)
app.include_router(quotation_router)
app.include_router(payment_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Amira-Email-Fallback-Proof"],
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
