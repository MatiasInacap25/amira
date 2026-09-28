# Amira backend

FastAPI starter application. It provides a health check and validated settings; it does not yet implement marketplace behavior or connect to external services.

## Requirements

- Python 3.12+
- `uv` (the project uses `pyproject.toml` and `uv.lock`)

## Setup

```powershell
uv sync
Copy-Item .env.example .env
uv run uvicorn amira_api.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive API documentation is at `/docs`. The health endpoint is `GET /health`.

Set `CORS_ORIGINS` to a comma-separated list of exact browser origins, including scheme and port, for example `http://localhost:3000`. Do not use wildcard origins when sending credentials. The API connects lazily when a database-backed request runs; Alembic reads `DATABASE_URL` and reports a clear error if migrations are run before one is configured.

## Public browse API

- `GET /api/services?q=&category=&location=&limit=20&offset=0` returns provider/service catalog entries.
- `GET /api/shared-routes?origin=&destination=&departureFrom=&departureTo=&limit=20&offset=0` returns published routes that accept requests, with ordered stop numbers and estimated times.

Both endpoints return `{items, total, limit, offset}`, cap page size at 50 and offset at 5000, and validate filter lengths. Responses intentionally omit account identity, company tax IDs, raw storage keys, full stop addresses, vehicles/drivers, customer requests, chats, payments, and payout references. Route results expose only published origin/destination cities; intermediate stops include sequence and time but no address because the current schema has no separate public-locality field. Service entries are based on `Servicios_Disponibles`; the current schema has no separate visibility status for that association. Logo URLs remain null until a safe public asset URL mechanism is implemented. Departure filters must be timezone-aware ISO-8601 datetimes.

## Checks

```powershell
uv run pytest
uv run python -c "from amira_api.main import app; print(app.title)"
uv lock --check
```

## Migrations

Alembic is initialized under `alembic/`. The declarative mappings live in `src/amira_api/models.py`; configure `DATABASE_URL` before applying migrations. Migrations are not run as part of tests and no live database is required for structural checks or offline PostgreSQL SQL generation.

## Database mapping

The ORM was mapped from the current Lucid diagram and its approved constraint notes, with English Python names and the diagram's Spanish table/column names retained in PostgreSQL. UUID primary keys use `gen_random_uuid()`; money uses fixed-precision `NUMERIC`, date-times are timezone-aware, and identity is linked by a unique Supabase Auth user UUID. Amira does not store a local password hash. `Vehiculo.Imagen_Storage_Key` is one required private-storage key; `Año` and `Peso_maximo` are optional.

`Usuario` is the complete account set. `Conductor` is a unique-user subset assigned to an employer `Perfil`; it is not itself the driver's public listing. A user may own at most one public profile, and that profile may exist without a driver record. `Rut_Empresa` is nullable because independent profiles do not require it; the profile's configured company role and any driver affiliation must be validated by the service layer because the diagram does not provide canonical role codes. `Cuenta_Desembolso` stores only a provider account reference, onboarding state, and timestamps. A payout records the destination account used for audit; no bank account, card, identity image, or credential is stored locally.

The schema enforces primary/foreign keys, one profile per user, one driver row per user, chat-member uniqueness, sender membership, one rating per service, normalized email/plate uniqueness, trip/vehicle assignment, same-trip stop references, provider-scoped external IDs/idempotency keys, and field-level checks. The current diagram contains 25 entities; `Cuenta_Desembolso` is added from its explicit Lucid note because the ERD shape is absent under the document's editing limit.

Cross-record and temporal rules remain business-transaction responsibilities unless a reviewed database trigger is installed: verify payment-provider signatures and state transitions; only reserve after successful payment; verify the quotation/chat/form/customer chain and preserve accepted commercial terms; lock capacity/exclusivity while confirming payment; validate trip ownership/roles and assignments; enforce pickup-before-delivery and publication prerequisites; keep refund-claim/payment-service references consistent; and release funds only after completion, notice, customer-conformity or the 24-hour rule, and claim checks. Foreign keys alone do not prove these invariants. RLS, grants, endpoint authorization, and public/private response shaping must be configured separately before exposing tables through Supabase Data API.

The logical ERD does not settle provider status vocabularies, canonical profile-role tokens, subcontracting policy, refund limits, currency/provider compatibility, or live concurrency and reconciliation behavior. Those are not inferred by the ORM; the application must define them before money-moving workflows are enabled.

The engine normalizes PostgreSQL URLs to Psycopg 3, requires TLS, and bounds the pool, connection timeout, and statement timeout. The public-browse migration enables RLS and revokes `PUBLIC`, `anon`, and `authenticated` privileges for all 26 application tables and `alembic_version`. It seeds clearly labeled `[DEMO]` rows with a synthetic non-login account mapping and `.invalid` email; it creates no Supabase Auth user, identity-verification, payment, or payout record.
