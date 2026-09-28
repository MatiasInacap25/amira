# Transport Services Marketplace

## Summary

A marketplace connecting customers with transport companies and independent truck drivers for moving, debris removal, merchandise transport, freight, and towing services. Customers submit a service request, discuss details in a chat, receive a quotation, and pay to confirm the service.

Providers can publish scheduled trips with spare capacity so multiple customers can share one journey, including intermediate pickups and deliveries. Each customer keeps a separate service, quotation, and chat. Providers validate cargo suitability using descriptions, photos, and estimated dimensions and weight rather than relying on an exact automatic space calculation. Customers can request an exclusive service that cannot share the vehicle with other loads during that service.

Registration includes identity verification through Didit, using an identity document and a live facial capture with liveness and face-matching checks.

## Approved Technology Stack

These choices are documented, not installed. The repository currently contains project documentation rather than a runnable frontend or backend.

### Frontend

| Technology | Role |
| --- | --- |
| Next.js App Router + React + TypeScript | Web pages, routing, and typed customer/provider interfaces |
| Tailwind CSS + shadcn/ui | Styling and reusable UI components |
| TanStack Query | Interactive API queries, mutations, caching, and invalidation |
| React Hook Form | Form state and field validation |
| Sonner | Transient success/error notifications; field errors remain inline |
| Lucide React | Icons |
| Native fetch | HTTP requests without an additional HTTP client |
| @supabase/supabase-js + @supabase/ssr | Supabase Auth integration with browser/server clients and cookie-based SSR |

Zod and @hookform/resolvers are not included initially. Use React Hook Form's built-in rules and custom validation, and validate every request independently in FastAPI. Reconsider schema-based frontend validation only if complex forms justify it. Next.js handles routing; do not add TanStack Router or a second form library.

### Backend and Managed Services

| Technology | Role |
| --- | --- |
| FastAPI + Uvicorn | API, business rules, and ASGI server |
| Pydantic | Request/response validation |
| SQLAlchemy 2.x | ORM, relationships, queries, and transactions |
| Alembic | Versioned database migrations |
| Psycopg 3 | PostgreSQL driver for SQLAlchemy |
| pydantic-settings | Environment-based configuration |
| HTTPX | Outbound requests to identity/payment providers and API testing |
| python-multipart | Multipart forms/files when handled by FastAPI |
| PyJWT[crypto] | Verify Supabase-issued JWT signatures and claims using the project's signing configuration; do not issue a second set of login tokens |
| Supabase PostgreSQL | Relational database |
| Supabase Auth | Registration, login, recovery, and managed credentials |
| Supabase Storage | Vehicle images and service attachments with appropriate access policies |
| Didit | External identity verification; separate from login authentication |
| External payment provider (not selected) | Hosted bank-data onboarding, payment collection, and compatible marketplace payouts |
| Docker | Package the backend for consistent deployment |

Supabase Auth owns passwords. Do not install pwdlib for local password handling or maintain Usuario.Hash_Contraseña as a second credential store. During ORM implementation, link Usuario to the Supabase Auth user identifier with a unique reference. FastAPI verifies token signature, expiration, issuer, and audience and separately enforces permissions. Never trust client-supplied user IDs as proof of identity or expose privileged Supabase keys.

Business-critical writes, including reservations, quotations, payments, and payouts, go through FastAPI. Protect any tables exposed through Supabase's Data API with appropriate RLS and grants; a direct privileged SQLAlchemy connection does not automatically inherit end-user authorization.

### Testing and Development Tools

| Technology | Role | Status |
| --- | --- | --- |
| pytest + HTTPX | Backend unit/integration tests | Selected; not installed in an application environment |
| Playwright | Browser end-to-end tests, including request/chat/payment sandbox flows | Selected; setup pending application scaffolding |
| Graphify | Development-time knowledge graph and architecture navigation; not a production dependency | Local skill present; CLI verification described below |

### Frontend Container Decision

Do not require Docker for the frontend initially. A managed Next.js deployment can build directly from source. Docker remains a supported option for self-hosting or a deployment platform that requires containers: it improves portability but adds image builds and runtime maintenance. Backend containerization is retained; frontend containerization is deferred until the hosting target warrants it.

### Graphify Verification

Verified on 2026-09-26: the project skill and AGENTS.md integration are present, and `uv tool list` reports graphifyy 0.9.65. `graphify --help`, Python module import, and file detection succeed outside the restricted sandbox. Detection found 15 supported files (2 classified as code and 13 as documents, including tooling references); this does not imply the application is scaffolded. Within the sandbox, the uv launcher/cache encounters permission errors; this is not evidence of a damaged installation. No graphify-out/graph.json exists yet. Graph generation is not part of this technology-documentation update.

### Diagram Limitations

The user reports adding Perfil.Rut_Empresa and Vehiculo.Imagen in Lucid. Cuenta_Desembolso remains part of the intended database schema even though the diagram's free-plan limit prevents adding its shape. The payment provider captures banking information; Amira stores only private account references, status, and timestamps.

## Identity Verification

Prefer provider-hosted document capture to avoid unnecessary local copies of identity photos. Store the user reference, provider, verification identifier, status, and timestamps. Confirm supported documents, pricing, retention, and deletion policies before production use.

## References

- [Next.js](https://nextjs.org/)
- [FastAPI](https://fastapi.tiangolo.com/)
- [Didit](https://didit.me/)
- [SQLAlchemy](https://docs.sqlalchemy.org/en/20/orm/)
- [Pydantic](https://docs.pydantic.dev/)
- [Alembic](https://alembic.sqlalchemy.org/)
- [TanStack Query](https://tanstack.com/query/latest/docs/framework/react/overview)
- [React Hook Form](https://react-hook-form.com/)
- [shadcn/ui](https://ui.shadcn.com/)
- [Supabase Auth SSR](https://supabase.com/docs/guides/auth/server-side/nextjs)
- [Next.js deployment options](https://nextjs.org/docs/app/getting-started/deploying)
- [Playwright](https://playwright.dev/docs/intro)
