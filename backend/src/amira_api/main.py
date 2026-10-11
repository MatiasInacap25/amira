from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amira_api.account_routes import router as account_router
from amira_api.chat_routes import router as chat_router
from amira_api.customer_routes import router as customer_router
from amira_api.fallback_routes import router as fallback_router
from amira_api.invitation_routes import router as invitation_router
from amira_api.location_routes import router as location_router
from amira_api.public_routes import router as public_router
from amira_api.settings import get_settings, warn_if_dev_sms_mfa_bypass_active

settings = get_settings()
warn_if_dev_sms_mfa_bypass_active(settings)
app = FastAPI(title=settings.app_name)
app.include_router(account_router)
app.include_router(chat_router)
app.include_router(customer_router)
app.include_router(fallback_router)
app.include_router(invitation_router)
app.include_router(location_router)
app.include_router(public_router)

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
