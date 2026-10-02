# Amira frontend

## Local configuration

The email/password and SMS account flow requires a Supabase project configured for email confirmation and phone MFA. Set these variables in the frontend runtime (for example in an untracked local environment file):

```text
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Only the Supabase project URL and publishable key are exposed to browser code. Never put a Supabase secret/service-role key in a `NEXT_PUBLIC_` variable. Configure the Supabase Auth email-confirmation redirect allowlist to include the deployed origin's `/auth/callback` route and enable phone MFA with a working SMS provider. Confirmation email delivery is handled by Supabase Auth; Amira's separate email-code fallback and invitation email delivery are not implemented in this frontend delivery. No live provider credentials are included.

`NEXT_PUBLIC_API_URL` must be explicitly configured as an absolute HTTP(S) URL. The account flow does not infer a localhost destination: missing or invalid configuration stops before sending an access token to the API. A loopback URL is only used when explicitly configured for local development.

After email confirmation, the callback verifies the Supabase user server-side, then the browser flow requires a verified phone factor before it calls the authenticated account API. Profile and role details are submitted only to the FastAPI account API; they are not stored as user-editable Supabase authorization metadata and the browser does not access application tables.

## Development

From this directory, run `npm run dev` and open [http://localhost:3000](http://localhost:3000). Verification commands are `npm run lint`, `npm run build`, and `npm run test:e2e`. E2E starts an isolated temporary app copy with `.env*` files excluded, explicit test-only loopback Supabase/API values, and a local fake Supabase endpoint; it never reuses an existing dev server or contacts a hosted project.

## Getting Started

First, run the development server:

```bash
npm run dev
# or
yarn dev
# or
pnpm dev
# or
bun dev
```

Open [http://localhost:3000](http://localhost:3000) with your browser to see the result.

You can start editing the page by modifying `app/page.tsx`. The page auto-updates as you edit the file.

This project uses [`next/font`](https://nextjs.org/docs/app/building-your-application/optimizing/fonts) to automatically optimize and load [Geist](https://vercel.com/font), a new font family for Vercel.

## Learn More

To learn more about Next.js, take a look at the following resources:

- [Next.js Documentation](https://nextjs.org/docs) - learn about Next.js features and API.
- [Learn Next.js](https://nextjs.org/learn) - an interactive Next.js tutorial.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
