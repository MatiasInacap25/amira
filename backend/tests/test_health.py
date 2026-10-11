import asyncio

import httpx

from amira_api.main import app


async def request_health() -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/health")


async def request_with_origin(origin: str) -> httpx.Response:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.get("/health", headers={"Origin": origin})


def test_health_endpoint_returns_ok() -> None:
    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_cors_allows_configured_origin_without_credentials() -> None:
    response = asyncio.run(request_with_origin("http://localhost:3000"))

    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-credentials" not in response.headers


def test_cors_does_not_allow_unconfigured_origin() -> None:
    response = asyncio.run(request_with_origin("https://untrusted.example"))

    assert "access-control-allow-origin" not in response.headers
