# Dev cloud demo deployment

This repository deploys as two services: the Next.js web application on Vercel and the FastAPI API on Render. Supabase remains a separately managed dependency for PostgreSQL and Auth. The checked-in Render Blueprint configures only the API service; it does not provision a database, Supabase project, or Vercel project.

## 1. Link the Git repository

Connect the same Git repository to Vercel and Render, then select the branch that should represent the dev demo. Keep the branch selection consistent between both platforms. The repository's linked branch is the deployment source; saving a local file does not deploy it. Pushing a commit to the selected branch triggers Vercel's Git deployment and Render's `autoDeployTrigger: commit` for the API when backend files change.

Vercel supports selecting a monorepo root directory during project setup. Set **Root Directory** to `frontend`; leave the detected Next.js framework and build commands at their defaults. Add the frontend environment variables below before the first deployment. Vercel then builds the frontend from that directory on commits to the configured branch. See [Vercel Git deployments](https://vercel.com/docs/git).

In Render, create a Blueprint instance from the linked repository and use the root-level `render.yaml`. It defines a Docker web service with `backend` as its root, the existing `backend/Dockerfile`, and `/health` as the health check. Its build filter limits API deploys to backend changes. See [Render Blueprint YAML](https://render.com/docs/blueprint-spec) and [Render monorepo support](https://render.com/docs/monorepo-support).

## 2. Configure the backend on Render

The Blueprint supplies `APP_NAME=Amira API`, `APP_ENV=development`, and the default JWT audience. Set the remaining values in the Render service's environment settings; keep credentials in Render's secret environment-variable store, not in this repository:

| Variable | Value / guidance |
| --- | --- |
| `DATABASE_URL` | Secret PostgreSQL connection URL for the dev Supabase database. The API requires PostgreSQL and enforces TLS. Use the connection URL intended for an external application, not a browser key. |
| `SUPABASE_JWT_ISSUER` | Supabase Auth JWT issuer URL for this project, as configured by Supabase. The API uses it to verify access-token issuer/signature. |
| `SUPABASE_JWT_AUDIENCE` | Keep `authenticated`, unless the Supabase project is configured differently. |
| `CORS_ORIGINS` | Exact deployed frontend origin, including `https://` and no path, e.g. `https://<your-vercel-domain>`. Add comma-separated exact origins only if more than one is needed. |
| `INDEPENDENT_DRIVER_TYPE_ID` | UUID of the approved `Tipo_Conductor` row, required for independent-driver account provisioning. |
| `COMPANY_DRIVER_TYPE_ID` | UUID of the approved `Tipo_Conductor` row if company owners may opt into a linked driver record. |

The two driver type IDs are trusted server-side mappings; do not accept them from browser input. The app's configuration and provisioning requirements are described in [`backend/README.md`](../backend/README.md).

## 3. Configure Vercel and Supabase Auth

Set these variables for the Vercel deployment environment that serves the dev demo:

| Variable | Value / guidance |
| --- | --- |
| `NEXT_PUBLIC_SUPABASE_URL` | URL of the dev Supabase project. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | That project's publishable key. This is browser-visible; never put a Supabase secret/service-role key in a `NEXT_PUBLIC_` variable. |
| `NEXT_PUBLIC_API_URL` | Public HTTPS origin of the Render API, without an `/api` suffix, e.g. `https://<your-api>.onrender.com`. |

These `NEXT_PUBLIC_` values are included in the browser bundle, so configure them before building/deploying and do not put credentials in them. After Vercel assigns a domain, add `https://<your-vercel-domain>/auth/callback` to Supabase Auth's email-confirmation redirect allowlist. Configure email confirmation and a working SMS provider/phone MFA for the account flow. See [`frontend/README.md`](../frontend/README.md) for the current auth-flow boundaries.

Set the Render `CORS_ORIGINS` to the same exact Vercel origin. The browser calls the API directly, so a missing/wrong API URL or CORS origin prevents the app from reaching it.

## 4. Apply database migrations

Before using database-backed browse/account features, set the dev database URL locally (do not commit it) and run from `backend/`:

```sh
uv sync
uv run alembic upgrade head
```

This applies the checked-in Alembic migrations, including the clearly marked `[DEMO]` browse fixtures. The fixture is synthetic and does not create a Supabase Auth user or payment/payout records. The migration also enables row-level security and revokes direct Data API access to application tables; the API's PostgreSQL connection serves database-backed routes. Re-run migrations when a future commit adds one. The Render Blueprint intentionally does not run migrations automatically, so schema changes remain an explicit operator step.

## 5. Deploy and verify

Push a commit to the linked branch after platform setup:

- Vercel creates a deployment for the configured frontend project/branch.
- Render automatically builds and deploys the API when the commit changes `backend/**`.
- Local saves alone do nothing; deployments follow Git pushes, not editor autosave.

Check the Vercel deployment URL, then request `https://<your-api>.onrender.com/health`; the API should return `{"status":"ok"}`. Browse pages that require seeded data only work after migrations complete. Account creation additionally needs the Supabase confirmation/MFA setup and server-side driver mappings above.

The demo currently has no wired Supabase Storage upload flow, identity-verification provider, or payment provider. Do not add production credentials or expect those workflows to work as part of this browse/auth demo.
