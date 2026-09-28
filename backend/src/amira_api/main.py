from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from amira_api.public_routes import router as public_router
from amira_api.settings import get_settings

settings = get_settings()
app = FastAPI(title=settings.app_name)
app.include_router(public_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}
